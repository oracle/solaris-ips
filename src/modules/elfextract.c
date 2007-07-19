#include <elf.h>
#include <gelf.h>

#include <sys/stat.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <fcntl.h>
#include <port.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <strings.h>

#include <sha1.h>

#include "liblist.h"
#include "elfextract.h"

char *
getident(int fd)
{
	char *id = NULL;

	if (!(id = malloc(EI_NIDENT)))
		return (NULL);
	
	lseek(fd, 0, SEEK_SET);
	read(fd, id, EI_NIDENT);

	return (id);
}

int
iself(int fd)
{
	char *ident;

	if (!(ident = getident(fd)))
		return (0);

	if (!strncmp(ident, ELFMAG, strlen(ELFMAG))) {
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
		return (0);

	return (ident[EI_CLASS] == ELFCLASS32);
}

Elf32_Ehdr *
gethead32(int fd)
{
	Elf32_Ehdr *hdr;

	if (!(hdr = malloc(sizeof(Elf32_Ehdr))))
		return (NULL);

	lseek(fd, 0, SEEK_SET);
	read(fd, hdr, sizeof(Elf32_Ehdr));

	return (hdr);
}

Elf64_Ehdr *
gethead64(int fd)
{
	Elf64_Ehdr *hdr;

	if (!(hdr = malloc(sizeof(Elf64_Ehdr))))
		return (NULL);

	lseek(fd, 0, SEEK_SET);
	read(fd, hdr, sizeof(Elf64_Ehdr));

	return (hdr);
}

static int
hashsection(off_t name, char *sh_table)
{
	if (!strcmp((char*)(name + sh_table),
		".text") ||
	    !strcmp((char*)(name + sh_table),
		".data") ||
	    !strcmp((char*)(name + sh_table),
		".data1") ||
	    !strcmp((char*)(name + sh_table),
		".rodata") ||
	    !strcmp((char*)(name + sh_table),
		".rodata1")) {
		return (1);
	}

	return (0);
}

/*
 * Reads a section in 1k increments, adding it 
 * to the hash.
 */
static void
readhash(int fd, SHA1_CTX *shc, off_t offset, off_t size)
{
	off_t n;
	char hashbuf[1024];

	if (!size)
		return;
	
	lseek(fd, offset, SEEK_SET);
	do {
		n = MIN(size, 1024);
		read(fd, hashbuf, n);
		SHA1Update(shc, hashbuf, n);
		size -= n;
	} while (size != 0);
}

/*
 * getdynamic32|64 - returns a struct filled with the
 * information we want from an ELF file.  Returns NULL
 * if it can't find everything (eg. not ELF file, wrong
 * class of ELF file).
 */
dyninfo_t *
getdynamic32(int fd)
{
	Elf32_Ehdr 	*hdr = gethead32(fd);
	Elf32_Shdr	*shdr = NULL;
	Elf32_Shdr	*heads = NULL;
	char		*sh_table = NULL;
	off_t		sh_size = 0;
	off_t		dynamic = 0, dsz = 0;
	Elf32_Dyn	*dt = NULL;
	off_t		verneed = 0, vernum = 0;
	long		numsect = 0, t = 0;
	off_t		rpath = 0, runpath = 0;
	char		*st = NULL;

	SHA1_CTX	shc;
	
	liblist_t	*deps = NULL;
	liblist_t	*vers = NULL;
	
	Elf32_Verneed	ev;
	Elf32_Vernaux	ea;
	off_t		n, a, p;
	
	/*
	 * Load section headers.  On the off chance that 
	 * there are more than 65,279 section entries to 
	 * this file, perform indirection.
	 */
	if (hdr->e_shnum == 0) {
		lseek(fd, hdr->e_shoff, SEEK_SET);
		if (!(shdr = malloc(sizeof(Elf32_Shdr))))
			return (NULL);
		read(fd, shdr, sizeof(Elf32_Shdr));
		numsect = shdr->sh_size;
		free(shdr);
	}
	else {
		numsect = hdr->e_shnum;
	}
	if (!(heads = malloc(numsect * sizeof(Elf32_Shdr))))
		return (NULL);
	lseek(fd, hdr->e_shoff, SEEK_SET);
	read(fd, heads, numsect * sizeof(Elf32_Shdr));

	/*
	 * Section header string table 
	 */
	if (hdr->e_shstrndx != SHN_XINDEX)
		shdr = &heads[hdr->e_shstrndx];
	else
		shdr = &heads[heads[0].sh_link];

	sh_size = shdr->sh_size;
	if (!(sh_table = malloc(sh_size)))
		return (NULL);
	lseek(fd, shdr->sh_offset, SEEK_SET);
	read(fd, sh_table, shdr->sh_size);


	/*
	 * Get useful sections
	 */
	SHA1Init(&shc);
	for (t=0; t < numsect; t++) {
		shdr = &heads[t];
		switch (shdr->sh_type) {
		case SHT_DYNAMIC:
			dynamic = shdr->sh_offset;
			dsz	= shdr->sh_size;
			break;
		case SHT_STRTAB:
			if (!strcmp((char*)(shdr->sh_name + sh_table), 
				            ".dynstr")) {

				if (!(st = malloc(shdr->sh_size))) {
					free(heads);
					return (NULL);
				}
				lseek(fd, shdr->sh_offset, SEEK_SET);
				read(fd, st, shdr->sh_size);
			}
			break;
		case SHT_PROGBITS:
			if (hashsection(shdr->sh_name, sh_table)) {
				readhash(fd, &shc, 
				    shdr->sh_offset, shdr->sh_size);
			}
			break;
		case SHT_SUNW_verneed:
			verneed = shdr->sh_offset;
			vernum = shdr->sh_link;
			break;
		}
	}
	free(heads);

	/* Didn't find some part? */
	if (!st || !dynamic || !verneed) {
		printf("elf: didn't find the triumvirate\n");
		free(st);
		return (NULL);
	}

	/* Parse dynamic section */
	if (!(deps = liblist_alloc())) {
		free(st);
		return (NULL);
	}
	if (!(dt = malloc(dsz))) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}
	lseek(fd, dynamic, SEEK_SET);
	read(fd, dt, dsz);
	for (t=0; t < (dsz / sizeof(Elf32_Dyn)); t++) {
		switch (dt[t].d_tag) {
			case DT_NEEDED:
				liblist_add(deps, (off_t)dt[t].d_un.d_val);
				break;
			case DT_RPATH:
				rpath = dt[t].d_un.d_val;
				break;
			case DT_RUNPATH:
				runpath = dt[t].d_un.d_val;
				break;
		}
	}
	free(dt);

	/* Runpath supercedes rpath, but use rpath if no runpath */
	if (!runpath)
		runpath = rpath;

	/*
	 * Finally, get version information for each item in 
	 * our dependency list.  This part is a little messier,
	 * as it seems that this is of unspecified length and 
	 * ordering, so we have to do a lot of seeking and reading.
	 */
	if (!(vers = liblist_alloc())) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}

	ev.vn_next = 0;
	
	lseek(fd, verneed, SEEK_SET);
	for (t=0; t < vernum; t++) {
		n = lseek(fd, ev.vn_next, SEEK_CUR);
		read(fd, &ev, sizeof(Elf32_Verneed));
		lseek(fd, n, SEEK_SET);

		liblist_t *veraux = NULL;
		if (!(veraux = liblist_alloc())) {
			liblist_free(deps);
			liblist_free(vers);
			free(st);
			return (NULL);
		}
		
		lseek(fd, ev.vn_aux, SEEK_CUR);
		ea.vna_next = 0;
		for (a = 0; a < ev.vn_cnt; a++) {
			p = lseek(fd, ea.vna_next, SEEK_CUR);
			read(fd, &ea, sizeof(Elf32_Vernaux));
			liblist_add(veraux, ea.vna_name);
			lseek(fd, p, SEEK_SET);
		}
		liblist_add(vers, ev.vn_file);
		vers->tail->verlist = veraux;

		lseek(fd, n, SEEK_SET);
	}

	/* Consolidate version and dependency information */
	liblist_foreach(deps, setver_liblist_cb, vers, NULL);
	liblist_free(vers);


	/*liblist_foreach(deps, print_liblist_cb, st, NULL);*/

	dyninfo_t *ret = NULL;
	if (!(ret = malloc(sizeof(dyninfo_t)))) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}

	ret->runpath = runpath;
	ret->st = st;
	ret->deps = deps;
	SHA1Final(ret->hash, &shc);

	return (ret);
}

dyninfo_t *
getdynamic64(int fd)
{
	Elf64_Ehdr 	*hdr = gethead64(fd);
	Elf64_Shdr	*shdr = NULL;
	Elf64_Shdr	*heads = NULL;
	char		*sh_table = NULL;
	off_t		sh_size = 0;
	off_t		dynamic = 0, dsz = 0;
	Elf64_Dyn	*dt = NULL;
	off_t		verneed = 0, vernum = 0;
	long		numsect = 0, t = 0;
	off_t		rpath = 0, runpath = 0;
	char		*st = NULL;
	
	SHA1_CTX	shc;
	
	liblist_t	*deps = NULL;
	liblist_t	*vers = NULL;
	
	Elf64_Verneed	ev;
	Elf64_Vernaux	ea;
	off_t		n, a, p;
	
	/*
	 * Load section headers.  On the off chance that 
	 * there are more than 65,279 section entries to 
	 * this file, perform indirection.
	 */
	if (hdr->e_shnum == 0) {
		lseek(fd, hdr->e_shoff, SEEK_SET);
		if (!(shdr = malloc(sizeof(Elf64_Shdr))))
			return (NULL);
		read(fd, shdr, sizeof(Elf64_Shdr));
		numsect = shdr->sh_size;
		free(shdr);
	}
	else {
		numsect = hdr->e_shnum;
	}
	if (!(heads = malloc(numsect * sizeof(Elf64_Shdr))))
		return (NULL);
	lseek(fd, hdr->e_shoff, SEEK_SET);
	read(fd, heads, numsect * sizeof(Elf64_Shdr));

	/*
	 * Section header string table 
	 */
	if (hdr->e_shstrndx != SHN_XINDEX)
		shdr = &heads[hdr->e_shstrndx];
	else
		shdr = &heads[heads[0].sh_link];

	sh_size = shdr->sh_size;
	if (!(sh_table = malloc(sh_size)))
		return (NULL);
	lseek(fd, shdr->sh_offset, SEEK_SET);
	read(fd, sh_table, shdr->sh_size);


	/*
	 * Get useful sections
	 */
	SHA1Init(&shc);
	for (t=0; t < numsect; t++) {
		shdr = &heads[t];
		switch (shdr->sh_type) {
		case SHT_DYNAMIC:
			dynamic = shdr->sh_offset;
			dsz	= shdr->sh_size;
			break;
		case SHT_STRTAB:
			if (!strcmp((char*)(shdr->sh_name + sh_table), 
				            ".dynstr")) {

				if (!(st = malloc(shdr->sh_size))) {
					free(heads);
					return (NULL);
				}
				lseek(fd, shdr->sh_offset, SEEK_SET);
				read(fd, st, shdr->sh_size);
			}
			break;
		case SHT_PROGBITS:
			if (hashsection(shdr->sh_name, sh_table)) {
				readhash(fd, &shc, 
				    shdr->sh_offset, shdr->sh_size);
			}
			break;
		case SHT_SUNW_verneed:
			verneed = shdr->sh_offset;
			vernum = shdr->sh_link;
			break;
		}
	}
	free(heads);

	/* Didn't find some part? */
	if (!st || !dynamic || !verneed) {
		printf("elf: didn't find the triumvirate\n");
		free(st);
		return (NULL);
	}

	/* Parse dynamic section */
	if (!(deps = liblist_alloc())) {
		free(st);
		return (NULL);
	}
	if (!(dt = malloc(dsz))) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}
	lseek(fd, dynamic, SEEK_SET);
	read(fd, dt, dsz);
	for (t=0; t < (dsz / sizeof(Elf64_Dyn)); t++) {
		switch (dt[t].d_tag) {
			case DT_NEEDED:
				liblist_add(deps, (off_t)dt[t].d_un.d_val);
				break;
			case DT_RPATH:
				rpath = dt[t].d_un.d_val;
				break;
			case DT_RUNPATH:
				runpath = dt[t].d_un.d_val;
				break;
		}
	}
	free(dt);

	/* Runpath supercedes rpath, but use rpath if no runpath */
	if (!runpath)
		runpath = rpath;

	/*
	 * Finally, get version information for each item in 
	 * our dependency list.  This part is a little messier,
	 * as it seems that this is of unspecified length and 
	 * ordering, so we have to do a lot of seeking and reading.
	 */
	if (!(vers = liblist_alloc())) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}

	ev.vn_next = 0;
	
	lseek(fd, verneed, SEEK_SET);
	for (t=0; t < vernum; t++) {
		n = lseek(fd, ev.vn_next, SEEK_CUR);
		read(fd, &ev, sizeof(Elf64_Verneed));
		lseek(fd, n, SEEK_SET);

		liblist_t *veraux = NULL;
		if (!(veraux = liblist_alloc())) {
			liblist_free(deps);
			liblist_free(vers);
			free(st);
			return (NULL);
		}
		
		lseek(fd, ev.vn_aux, SEEK_CUR);
		ea.vna_next = 0;
		for (a = 0; a < ev.vn_cnt; a++) {
			p = lseek(fd, ea.vna_next, SEEK_CUR);
			read(fd, &ea, sizeof(Elf64_Vernaux));
			liblist_add(veraux, ea.vna_name);
			lseek(fd, p, SEEK_SET);
		}
		liblist_add(vers, ev.vn_file);
		vers->tail->verlist = veraux;

		lseek(fd, n, SEEK_SET);
	}

	/* Consolidate version and dependency information */
	liblist_foreach(deps, setver_liblist_cb, vers, NULL);
	liblist_free(vers);


	/*liblist_foreach(deps, print_liblist_cb, st, NULL);*/

	dyninfo_t *ret = NULL;
	if (!(ret = malloc(sizeof(dyninfo_t)))) {
		liblist_free(deps);
		free(st);
		return (NULL);
	}

	ret->runpath = runpath;
	ret->st = st;
	ret->deps = deps;
	SHA1Final(ret->hash, &shc);

	return (ret);
}

