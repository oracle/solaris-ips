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
 *  Copyright (c) 2009, 2016, Oracle and/or its affiliates. All rights reserved.
 */

#include <libelf.h>
#include <gelf.h>

#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <strings.h>
#include <string.h>
#include <netinet/in.h>
#include <inttypes.h>
#if defined(__SVR4) && defined(__sun)
/* Solaris has built-in SHA-1 and SHA-2 library interfaces */
#include <sha1.h>
#include <sha2.h>
#else
/*
 * All others can use OpenSSL, but OpenSSL's method signatures
 * are slightly different
 */
#include <openssl/sha.h>
#define	SHA1_CTX SHA_CTX
#define	SHA1Update SHA1_Update
#define	SHA1Init SHA1_Init
#define	SHA1Final SHA1_Final
#endif

#include <liblist.h>
#include <elfextract.h>

char *
pkg_string_from_type(int type)
{
	switch (type) {
	case ET_EXEC:
		return ("exe");
	case ET_DYN:
		return ("so");
	case ET_CORE:
		return ("core");
	case ET_REL:
		return ("rel");
	default:
		return ("other");
	}
}

char *
pkg_string_from_arch(int arch)
{
	switch (arch) {
	case EM_NONE:
		return ("none");
	case EM_SPARC:
	case EM_SPARC32PLUS:
	case EM_SPARCV9:
		return ("sparc");
	case EM_386:
#if defined(__SVR4) && defined(__sun)
/* Solaris calls x86_64 "amd64", and recognizes 486 */
	case EM_486:
	case EM_AMD64:
#else
	case EM_X86_64:
#endif
		return ("i386");
	case EM_PPC:
	case EM_PPC64:
		return ("ppc");
	default:
		return ("other");
	}
}

char *
pkg_string_from_data(int data)
{
	switch (data) {
	case ELFDATA2LSB:
		return ("lsb");
	case ELFDATA2MSB:
		return ("msb");
	default:
		return ("unknown");
	}
}

char *
pkg_string_from_osabi(int osabi)
{
	switch (osabi) {
	case ELFOSABI_NONE:
	/* case ELFOSABI_SYSV: */
		return ("none");
	case ELFOSABI_LINUX:
		return ("linux");
	case ELFOSABI_SOLARIS:
		return ("solaris");
	default:
		return ("other");
	}
}

static char *
getident(int fd)
{
	char *id = NULL;

	if ((id = malloc(EI_NIDENT)) == NULL) {
		(void) PyErr_NoMemory();
		return (NULL);
	}

	if (lseek(fd, 0, SEEK_SET) == -1) {
		PyErr_SetFromErrno(PyExc_IOError);
		free(id);
		return (NULL);
	}

	if (read(fd, id, EI_NIDENT) < 0) {
		PyErr_SetFromErrno(PyExc_IOError);
		free(id);
		return (NULL);
	}

	return (id);
}

int
iself(int fd)
{
	char *ident;

	if (!(ident = getident(fd)))
		return (-1);

	if (strncmp(ident, ELFMAG, strlen(ELFMAG)) == 0) {
		free(ident);
		return (1);
	}

	free(ident);
	return (0);
}

int
iself32(int fd)
{
	char *ident = NULL;

	if (!(ident = getident(fd)))
		return (-1);

	if (ident[EI_CLASS] == ELFCLASS32) {
		free(ident);
		return (1);
	}

	free(ident);
	return (0);
}

static GElf_Ehdr *
gethead(Elf *elf)
{
	GElf_Ehdr *hdr;

	if (!elf) {
		PyErr_SetString(PyExc_ValueError,
		    "elf.so`gethead: argument 'elf' must not be NULL");
		return (NULL);
	}

	if ((hdr = malloc(sizeof (GElf_Ehdr))) == NULL) {
		(void) PyErr_NoMemory();
		return (NULL);
	}

	if (gelf_getehdr(elf, hdr) == 0) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		free(hdr);
		return (NULL);
	}

	return (hdr);
}

hdrinfo_t *
getheaderinfo(int fd)
{
	Elf *elf;
	GElf_Ehdr *hdr;
	hdrinfo_t *hi;

	if ((hi = malloc(sizeof (hdrinfo_t))) == NULL) {
		(void) PyErr_NoMemory();
		return (NULL);
	}

	if (elf_version(EV_CURRENT) == EV_NONE) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		free(hi);
		return (NULL);
	}

	if (!(elf = elf_begin(fd, ELF_C_READ, NULL))) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		free(hi);
		return (NULL);
	}

	if (!(hdr = gethead(elf))) {
		(void) elf_end(elf);
		free(hi);
		return (NULL);
	}

	hi->type = hdr->e_type;
	hi->bits = hdr->e_ident[EI_CLASS] == ELFCLASS32 ? 32 : 64;
	hi->arch = hdr->e_machine;
	hi->data = hdr->e_ident[EI_DATA];
	hi->osabi = hdr->e_ident[EI_OSABI];
	free(hdr);

	(void) elf_end(elf);

	return (hi);
}

typedef struct hashcb_data {
	char		*base;
	SHA1_CTX	*s1c;
	SHA256_CTX	*s2c;
} hashcb_data_t;

/*
 * Hashes a range from an mmap'd elf file
 */
static void
elfhash_cb(size_t offset, size_t size, void *udata)
{
	hashcb_data_t *h = (hashcb_data_t *)udata;

	if (!size)
		return;

	if (h->s1c != NULL) {
		SHA1Update(h->s1c, h->base + offset, size);
	}

	if (h->s2c != NULL) {
		SHA256Update(h->s2c, h->base + offset, size);
	}
}

/*
 * getdynamic - returns a struct filled with the
 * information we want from an ELF file.  Returns NULL
 * if it can't find everything (eg. not ELF file, wrong
 * class of ELF file).
 */
dyninfo_t *
getdynamic(int fd)
{
	Elf		*elf = NULL;
	Elf_Scn		*scn = NULL;
	GElf_Shdr	shdr;
	Elf_Data	*data_dyn = NULL;
	Elf_Data	*data_verneed = NULL, *data_verdef = NULL;
	GElf_Dyn	gd;

	char		*name = NULL;
	size_t		sh_str = 0;
	size_t		vernum = 0, verdefnum = 0;
	int		t = 0, num_dyn = 0, dynstr = -1;

	SHA1_CTX	shc;
	SHA256_CTX	shc2;
	dyninfo_t	*dyn = NULL;

	liblist_t	*deps = NULL;
	off_t		rpath = 0, runpath = 0, def = 0;

	/* Verneed */
	int a = 0;
	char *buf = NULL, *cp = NULL;
	GElf_Verneed *ev = NULL;
	GElf_Vernaux *ea = NULL;
	liblist_t *vers = NULL;

	GElf_Verdef *vd = NULL;
	GElf_Verdaux *va = NULL;
	liblist_t *verdef = NULL;

	if (elf_version(EV_CURRENT) == EV_NONE) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		return (NULL);
	}

	if (!(elf = elf_begin(fd, ELF_C_READ, NULL))) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		goto bad;
	}

	if (!elf_getshstrndx(elf, &sh_str)) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		goto bad;
	}

	/* get useful sections */
	while ((scn = elf_nextscn(elf, scn))) {
		if (gelf_getshdr(scn, &shdr) != &shdr) {
			PyErr_SetString(ElfError, elf_errmsg(-1));
			goto bad;
		}

		if (!(name = elf_strptr(elf, sh_str, shdr.sh_name))) {
			PyErr_SetString(ElfError, elf_errmsg(-1));
			goto bad;
		}

		switch (shdr.sh_type) {
		case SHT_DYNAMIC:
			if (!(data_dyn = elf_getdata(scn, NULL))) {
				PyErr_SetString(ElfError, elf_errmsg(-1));
				goto bad;
			}

			num_dyn = shdr.sh_size / shdr.sh_entsize;
			dynstr = shdr.sh_link;
			break;

#ifdef SHT_SUNW_verdef
		case SHT_SUNW_verdef:
#else
		case SHT_GNU_verdef:
#endif
			if (!(data_verdef = elf_getdata(scn, NULL))) {
				PyErr_SetString(ElfError, elf_errmsg(-1));
				goto bad;
			}

			verdefnum = shdr.sh_info;
			break;

#ifdef SHT_SUNW_verneed
		case SHT_SUNW_verneed:
#else
		case SHT_GNU_verneed:
#endif
			if (!(data_verneed = elf_getdata(scn, NULL))) {
				PyErr_SetString(ElfError, elf_errmsg(-1));
				goto bad;
			}

			vernum = shdr.sh_info;
			break;
		}
	}

	/* Dynamic but no string table? */
	if (data_dyn && dynstr < 0) {
		PyErr_SetString(ElfError,
		    "bad elf: didn't find the dynamic duo");
		goto bad;
	}

	/* Parse dynamic section */
	if (!(deps = liblist_alloc()))
		goto bad;

	for (t = 0; t < num_dyn; t++) {
		if (gelf_getdyn(data_dyn, t, &gd) == NULL) {
			PyErr_SetString(ElfError, elf_errmsg(-1));
			goto bad;
		}

		switch (gd.d_tag) {
		case DT_NEEDED:
		case DT_AUDIT:
		case DT_DEPAUDIT:
		case DT_FILTER:
		case DT_SUNW_FILTER:
			if (liblist_add(deps, gd.d_un.d_val) == NULL)
				goto bad;
			break;
		case DT_RPATH:
			rpath = gd.d_un.d_val;
			break;
		case DT_RUNPATH:
			runpath = gd.d_un.d_val;
			break;
		case DT_POSFLAG_1:
			if (gd.d_un.d_val & DF_P1_DEFERRED) {
				t++;
			}
		}
	}

	/* Runpath supercedes rpath, but use rpath if no runpath */
	if (!runpath)
		runpath = rpath;

	/*
	 * Finally, get version information for each item in
	 * our dependency list.  This part is a little messier,
	 * as it seems that libelf / gelf do not implement this.
	 */
	if (!(vers = liblist_alloc()))
		goto bad;

	if (vernum > 0 && data_verneed) {
		buf = data_verneed->d_buf;
		cp = buf;
	}

	for (t = 0; t < vernum; t++) {
		liblist_t *veraux = NULL;
		if (ev)
			cp += ev->vn_next;
		ev = (GElf_Verneed*)cp;

		if (!(veraux = liblist_alloc()))
			goto bad;

		buf = cp;

		cp += ev->vn_aux;

		ea = NULL;
		for (a = 0; a < ev->vn_cnt; a++) {
			if (ea)
				cp += ea->vna_next;
			ea = (GElf_Vernaux*)cp;
			if (liblist_add(veraux, ea->vna_name) == NULL) {
				liblist_free(veraux);
				goto bad;
			}
		}

		if (liblist_add(vers, ev->vn_file) == NULL) {
			liblist_free(veraux);
			goto bad;
		}
		vers->tail->verlist = veraux;

		cp = buf;
	}

	/* Consolidate version and dependency information */
	if (liblist_foreach(deps, setver_liblist_cb, vers, NULL) == -1)
		goto bad;
	liblist_free(vers);
	vers = NULL;

	/*
	 * Now, figure out what versions we provide.
	 */

	if (!(verdef = liblist_alloc()))
		goto bad;

	if (verdefnum > 0 && data_verdef) {
		buf = data_verdef->d_buf;
		cp = buf;
	}

	for (t = 0; t < verdefnum; t++) {
		if (vd)
			cp += vd->vd_next;
		vd = (GElf_Verdef*)cp;

		buf = cp;
		cp += vd->vd_aux;

		va = NULL;
		for (a = 0; a < vd->vd_cnt; a++) {
			if (va)
				cp += va->vda_next;
			va = (GElf_Verdaux*)cp;
			/* first one is name, rest are versions */
			if (!def)
				def = va->vda_name;
			else if (liblist_add(verdef, va->vda_name) == NULL)
				goto bad;
		}

		cp = buf;
	}

	if ((dyn = malloc(sizeof (dyninfo_t))) == NULL) {
		(void) PyErr_NoMemory();
		goto bad;
	}

	dyn->runpath = runpath;
	dyn->dynstr = dynstr;
	dyn->elf = elf;
	dyn->deps = deps;
	dyn->def = def;
	dyn->vers = verdef;
	return (dyn);

bad:
	if (deps)
		liblist_free(deps);
	if (verdef)
		liblist_free(verdef);
	if (vers)
		liblist_free(vers);
	if (elf)
		(void) elf_end(elf);
	return (NULL);
}

void
dyninfo_free(dyninfo_t *dyn)
{
	liblist_free(dyn->deps);
	liblist_free(dyn->vers);
	(void) elf_end(dyn->elf);
	free(dyn);
}

/*
 * gethashes - returns a struct filled with the hashes computed from an ELF
 * file.  Returns NULL if it encounters a problem (eg. not ELF file, offset out
 * of range).
 */
hashinfo_t *
gethashes(int fd, int dosha1, int dosha2)
{
	hashinfo_t	*hashes = NULL;
	hashcb_data_t	hdata = { NULL, NULL, NULL };
	Elf		*elf;
	struct stat	status;

	if ((elf_version(EV_CURRENT) == EV_NONE) ||
	    ((elf = elf_begin(fd, ELF_C_READ, NULL)) == NULL)) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		return (NULL);
	}

	if ((fstat(fd, &status) == -1) ||
	    ((hdata.base = mmap(NULL, status.st_size, PROT_READ, MAP_PRIVATE,
	    fd, 0)) == MAP_FAILED)) {
		PyErr_SetString(ElfError, strerror(errno));
		goto hash_out;
	}

	if (dosha1 > 0) {
		hdata.s1c = (SHA1_CTX *)malloc(sizeof (SHA1_CTX));
		if (hdata.s1c == NULL) {
			(void) PyErr_NoMemory();
			goto hash_out;
		}
		SHA1Init(hdata.s1c);
	}

	if (dosha2 > 0) {
		hdata.s2c = (SHA256_CTX *)malloc(sizeof (SHA256_CTX));
		if (hdata.s2c == NULL) {
			(void) PyErr_NoMemory();
			goto hash_out;
		}
		SHA256Init(hdata.s2c);
	}

	if (!gelf_sign_range(elf, elfhash_cb, ELF_SR_INTERPRET, &hdata)) {
		PyErr_SetString(ElfError, elf_errmsg(-1));
		goto hash_out;
	}

	if ((hashes = malloc(sizeof (hashinfo_t))) == NULL) {
		(void) PyErr_NoMemory();
		goto hash_out;
	}

	if (dosha1 > 0) {
		SHA1Final(hashes->hash, hdata.s1c);
	}

	if (dosha2 > 0) {
		SHA256Final(hashes->hash256, hdata.s2c);
	}

hash_out:
	(void) elf_end(elf);

	if (hdata.base)
		munmap(hdata.base, status.st_size);

	if (hdata.s1c)
		free(hdata.s1c);

	if (hdata.s2c)
		free(hdata.s2c);

	return (hashes);
}
