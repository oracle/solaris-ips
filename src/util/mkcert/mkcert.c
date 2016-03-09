/*
 * CDDL HEADER START
 *
 * The contents of this file are subject to the terms of the
 * Common Development and Distribution License (the "License").
 * You may not use this file except in compliance with the License.
 *
 * You can obtain a copy of the license at usr/src/OPENSOLARIS.LICENSE
 * or http://www.opensolaris.org/os/licensing.
 * See the License for the specific language governing permissions
 * and limitations under the License.
 *
 * When distributing Covered Code, include this CDDL HEADER in each
 * file and include the License file at usr/src/OPENSOLARIS.LICENSE.
 * If applicable, add the following below this CDDL HEADER, with the
 * fields enclosed by brackets "[]" replaced with your own identifying
 * information: Portions Copyright [yyyy] [name of copyright owner]
 *
 * CDDL HEADER END
 */

/*
 * Copyright (c) 2016, Oracle and/or its affiliates. All rights reserved.
 */

/*
 * Certificate creation. Demonstrates some certificate related
 * operations.
 */


#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <openssl/pem.h>
#include <openssl/conf.h>
#include <openssl/x509v3.h>
#ifndef OPENSSL_NO_ENGINE
#include <openssl/engine.h>
#endif

int mkcert(X509 **x509p, EVP_PKEY **pkeyp, int bits, int serial, int days);
int add_ext(X509 *cert, int nid, char *value);

int
main(int argc, char **argv)
{
	BIO *bio_err;
	X509 *x509 = NULL;
	EVP_PKEY *pkey = NULL;
	FILE *fp = NULL;

	CRYPTO_mem_ctrl(CRYPTO_MEM_CHECK_ON);

	bio_err = BIO_new_fp(stderr, BIO_NOCLOSE);

	mkcert(&x509, &pkey, 1024, 0, 365);

	RSA_print_fp(stdout, pkey->pkey.rsa, 0);
	X509_print_fp(stdout, x509);

	fp = fopen("cust_key.pem", "w");
	PEM_write_PrivateKey(fp, pkey, NULL, NULL, 0, NULL, NULL);
	fp = fopen("cust_cert.pem", "w");
	PEM_write_X509(fp, x509);

	X509_free(x509);
	EVP_PKEY_free(pkey);

#ifndef OPENSSL_NO_ENGINE
	ENGINE_cleanup();
#endif
	CRYPTO_cleanup_all_ex_data();

	CRYPTO_mem_leaks(bio_err);
	BIO_free(bio_err);
	return (0);
}

static void callback(int p, int n, void *arg)
{
	char c = 'B';

	if (p == 0) c = '.';
	if (p == 1) c = '+';
	if (p == 2) c = '*';
	if (p == 3) c = '\n';
	fputc(c, stderr);
}

int
mkcert(X509 **x509p, EVP_PKEY **pkeyp, int bits, int serial, int days)
{
	X509 *x;
	EVP_PKEY *pk;
	RSA *rsa;
	X509_NAME *name = NULL;

	if ((pkeyp == NULL) || (*pkeyp == NULL)) {
		if ((pk = EVP_PKEY_new()) == NULL) {
			abort();
		}
	}
	else
		pk = *pkeyp;

	if ((x509p == NULL) || (*x509p == NULL)) {
		if ((x = X509_new()) == NULL)
			goto err;
	}
	else
		x = *x509p;

	rsa = RSA_generate_key(bits, RSA_F4, callback, NULL);
	if (!EVP_PKEY_assign_RSA(pk, rsa)) {
		abort();
	}
	rsa = NULL;

	X509_set_version(x, 2);
	ASN1_INTEGER_set(X509_get_serialNumber(x), serial);
	X509_gmtime_adj(X509_get_notBefore(x), 0);
	X509_gmtime_adj(X509_get_notAfter(x), (long)60*60*24*days);
	X509_set_pubkey(x, pk);

	name = X509_get_subject_name(x);

	/*
	 * This function creates and adds the entry, working out the
	 * correct string type and performing checks on its length.
	 * Normally we'd check the return value for errors...
	 */
	X509_NAME_add_entry_by_txt(name, "C",
	    MBSTRING_ASC, (unsigned char *)"US", -1, -1, 0);
	X509_NAME_add_entry_by_txt(name, "ST",
	    MBSTRING_ASC, (unsigned char *)"California", -1, -1, 0);
	X509_NAME_add_entry_by_txt(name, "L",
	    MBSTRING_ASC, (unsigned char *)"Santa Clara", -1, -1, 0);
	X509_NAME_add_entry_by_txt(name, "O",
	    MBSTRING_ASC, (unsigned char *)"pkg5", -1, -1, 0);
	X509_NAME_add_entry_by_txt(name, "CN",
	    MBSTRING_ASC, (unsigned char *)"OpenSSL Group", -1, -1, 0);

	/*
	 * Its self signed so set the issuer name to be the same as the
	 * subject.
	 */
	X509_set_issuer_name(x, name);


#ifdef CUSTOM_EXT
	/* Maybe even add our own extension based on existing */
	{
		int nid;
		nid = OBJ_create("1.2.3.4", "MyAlias",
		    "My Test Alias Extension");
		X509V3_EXT_add_alias(nid, NID_netscape_comment);
		add_ext(x, nid, "critical,example comment alias");
	}
#endif

	if (!X509_sign(x, pk, EVP_sha256()))
		goto err;

	*x509p = x;
	*pkeyp = pk;
	return (1);
err:
	return (0);
}

/*
 * Add extension using V3 code: we can set the config file as NULL
 * because we wont reference any other sections.
 */

int
add_ext(X509 *cert, int nid, char *value)
{
	X509_EXTENSION *ex;
	X509V3_CTX ctx;
	/* This sets the 'context' of the extensions. */
	/* No configuration database */
	X509V3_set_ctx_nodb(&ctx);
	/*
	 * Issuer and subject certs: both the target since it is self signed,
	 * no request and no CRL
	 */
	X509V3_set_ctx(&ctx, cert, cert, NULL, NULL, 0);
	ex = X509V3_EXT_conf_nid(NULL, &ctx, nid, value);
	if (!ex)
		return (0);

	X509_add_ext(cert, ex, -1);
	X509_EXTENSION_free(ex);
	return (1);
}
