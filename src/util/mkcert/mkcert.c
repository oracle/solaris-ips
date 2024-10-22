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
 * Copyright (c) 2016, 2024, Oracle and/or its affiliates.
 */

/*
 * Generate a test certificate with a custom extension.  This is easier
 * done in C code than via Python cryptography or OpenSSL interfaces.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>

#include <openssl/pem.h>
#include <openssl/conf.h>
#include <openssl/x509v3.h>

static bool
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
	/* set config as NULL to avoid referencing any sections */
	ex = X509V3_EXT_conf_nid(NULL, &ctx, nid, value);
	if (!ex) {
		return (false);
	}

	X509_add_ext(cert, ex, -1);
	X509_EXTENSION_free(ex);
	return (true);
}

int
main(int argc, char **argv)
{
	X509 *cert;
	EVP_PKEY *pkey;
	X509_NAME *name = NULL;

	cert = X509_new();
	if (cert == NULL) {
		fprintf(stderr, "X509_new() failed\n");
		abort();
	}

	pkey = EVP_RSA_gen(4096);
	if (pkey == NULL) {
		fprintf(stderr, "EVP_RSA_gen() failed\n");
		abort();
	}

	X509_set_version(cert, 2);
	ASN1_INTEGER_set(X509_get_serialNumber(cert), 0);
	X509_gmtime_adj(X509_get_notBefore(cert), 0);
	X509_gmtime_adj(X509_get_notAfter(cert), (long)60*60*24*365);
	X509_set_pubkey(cert, pkey);

	name = X509_get_subject_name(cert);

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
	    MBSTRING_ASC, (unsigned char *)"IPS Gate Test", -1, -1, 0);

	/*
	 * Its self signed so set the issuer name to be the same as the
	 * subject.
	 */
	X509_set_issuer_name(cert, name);


	/* Add our own custom extension */
	int nid;
	nid = OBJ_create("1.2.3.4", "MyAlias", "My Test Alias Extension");
	X509V3_EXT_add_alias(nid, NID_netscape_comment);
	if (!add_ext(cert, nid, "critical,example comment alias")) {
		fprintf(stderr, "Failed to add custom extension.\n");
		return (1);
	}

	if (!X509_sign(cert, pkey, EVP_sha256())) {
		fprintf(stderr, "Failed to sign certificate.\n");
		return (1);
	}

	EVP_PKEY_print_public_fp(stdout, pkey, 0, NULL);
	X509_print_fp(stdout, cert);

	FILE *fp = fopen("cust_key.pem", "w");
	PEM_write_PrivateKey(fp, pkey, NULL, NULL, 0, NULL, NULL);
	(void) fclose(fp);
	fp = fopen("cust_cert.pem", "w");
	PEM_write_X509(fp, cert);
	(void) fclose(fp);

	X509_free(cert);
	EVP_PKEY_free(pkey);

	return (0);
}
