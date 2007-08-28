#include <libelf.h>
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
pkg_string_from_type(int type)
{
	switch (type) {
	case ET_EXEC:
		return "exe";
	case ET_DYN:
		return "so";
	case ET_CORE:
		return "core";
	case ET_REL:
		return "rel";
	default:
		return "other";
	}
}

char *
pkg_string_from_arch(int arch)
{
	switch (arch) {
	case EM_NONE:
		return "none";
	case EM_SPARC:
	case EM_SPARC32PLUS:
	case EM_SPARCV9:
		return "sparc";
	case EM_386:
	case EM_486:
	case EM_AMD64:
		return "i386";
	case EM_PPC:
	case EM_PPC64:
		return "ppc";
	default:
		return "other";
	}
}

char *
pkg_string_from_data(int data)
{
	switch (data) {
	case ELFDATA2LSB:
		return "lsb";
	case ELFDATA2MSB:
		return "msb";
	default:
		return "unknown";
	}
}

char *
pkg_string_from_osabi(int osabi)
{
	switch (osabi) {
	case ELFOSABI_NONE:
	/*case ELFOSABI_SYSV:*/
		return "none";
	case ELFOSABI_LINUX:
		return "linux";
	case ELFOSABI_SOLARIS:
		return "solaris";
	default:
		return "other";
	}
}

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

static GElf_Ehdr *
gethead(Elf *elf)
{
	GElf_Ehdr *hdr;

	if (!elf)
		return (NULL);
	
	if (!(hdr = malloc(sizeof(GElf_Ehdr))))
		return (NULL);

	if (gelf_getehdr(elf, hdr) == 0)
		return (NULL);


	return (hdr);
}

hdrinfo_t *
getheaderinfo(int fd)
{
	Elf *elf;
	GElf_Ehdr *hdr;
	hdrinfo_t *hi;

	if (!iself(fd))
		return (NULL);

	if (!(hi = malloc(sizeof(hdrinfo_t))))
		return (NULL);

	if (elf_version(EV_CURRENT) == EV_NONE)
		return (NULL);

	if (!(elf = elf_begin(fd, ELF_C_READ, NULL))) {
		free(hi);
		return (NULL);
	}
	
	if (!(hdr = gethead(elf))) {
		elf_end(elf);
		return (NULL);
	}

	hi->type = hdr->e_type;
	hi->bits = hdr->e_ident[EI_CLASS] == ELFCLASS32 ? 32 : 64;
	hi->arch = hdr->e_machine;
	hi->data = hdr->e_ident[EI_DATA];
	hi->osabi = hdr->e_ident[EI_OSABI];
	free(hdr);
	
	elf_end(elf);

	return (hi);
}

static int
hashsection(char *name)
{
	if (strcmp(name, ".SUNW_signature") == 0 ||
	    strcmp(name, ".comment") == 0 ||
	    strcmp(name, ".SUNW_ctf") == 0 ||
	    strcmp(name, ".debug") == 0 ||
	    strcmp(name, ".plt") == 0 ||
	    strcmp(name, ".rela.bss") == 0 ||
	    strcmp(name, ".rela.plt") == 0 ||
	    strcmp(name, ".line") == 0 ||
	    strcmp(name, ".note") == 0 ||
	    strcmp(name, ".compcom") == 0)
		return (0);

	return (1);
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
	GElf_Ehdr	hdr;
	GElf_Shdr	shdr;
	Elf_Data	*data_dyn = NULL;
	Elf_Data	*data_verneed = NULL, *data_verdef = NULL;
	GElf_Dyn	gd;

	char		*name = NULL;
	size_t		sh_str = 0;
	size_t		vernum = 0, verdefnum = 0;
	int		t = 0, num_dyn, dynstr = -1;
	
	SHA1_CTX	shc;
	dyninfo_t	*dyn = NULL;

	liblist_t	*deps = NULL;
	off_t		rpath = 0, runpath = 0, def = 0;
	
	if (elf_version(EV_CURRENT) == EV_NONE)
		return (NULL);

	if (!(elf = elf_begin(fd, ELF_C_READ, NULL))) {
		return (NULL);
	}
	
	if (!elf_getshstrndx(elf, &sh_str))
                return (NULL);

	/* get useful sections */
	SHA1Init(&shc);
	while ((scn = elf_nextscn(elf, scn))) {
		if (gelf_getshdr(scn, &shdr) != &shdr)
			return (NULL);

                if (!(name = elf_strptr(elf, sh_str, shdr.sh_name)))
			return (NULL);

		if (hashsection(name))
			readhash(fd, &shc, shdr.sh_offset, shdr.sh_size);

		switch (shdr.sh_type) {
		case SHT_DYNAMIC:
			if (!(data_dyn = elf_getdata(scn, NULL))) {
				elf_end(elf);
				return (NULL);
			}
			num_dyn = shdr.sh_size / shdr.sh_entsize;
			break;

		case SHT_STRTAB:
			if (strcmp(name, ".dynstr") == 0)
				dynstr = elf_ndxscn(scn);
			break;

		case SHT_SUNW_verdef:
			if (!(data_verdef = elf_getdata(scn, NULL))) {
				elf_end(elf);
				return (NULL);
			}
			verdefnum = shdr.sh_info;
			break;

		case SHT_SUNW_verneed:
			if (!(data_verneed = elf_getdata(scn, NULL))) {
				elf_end(elf);
				return (NULL);
			}
			vernum = shdr.sh_info;
			break;
		}
	}

	/* Dynamic but no string table? */
	if (data_dyn && (dynstr < 0)) {
		printf("bad elf: didn't find the dynamic duo\n");
		elf_end(elf);
		return (NULL);
	}

	/* Parse dynamic section */
	if (!(deps = liblist_alloc())) {
		elf_end(elf);
		return (NULL);
	}
	for (t = 0; t < num_dyn; t++) {
		gelf_getdyn(data_dyn, t, &gd);
		switch (gd.d_tag) {
		case DT_NEEDED:
			liblist_add(deps, gd.d_un.d_val);
			break;
		case DT_RPATH:
			rpath = gd.d_un.d_val;
			break;
		case DT_RUNPATH:
			runpath = gd.d_un.d_val;
			break;
		}
	}

	/* Runpath supercedes rpath, but use rpath if no runpath */
	if (!runpath)
		runpath = rpath;

	/* Verneed */
	int a = 0;
	char *buf = NULL, *cp = NULL;
	GElf_Verneed *ev = NULL;
	GElf_Vernaux *ea = NULL;
	liblist_t *vers = NULL;

	/*
	 * Finally, get version information for each item in 
	 * our dependency list.  This part is a little messier,
	 * as it seems that libelf / gelf do not implement this.
	 */
	if (!(vers = liblist_alloc())) {
		liblist_free(deps);
		elf_end(elf);
		return (NULL);
	}

	if (vernum > 0 && data_verneed) {
		buf = data_verneed->d_buf;
		cp = buf;
	}
	
	for (t=0; t < vernum; t++) {
		if (ev)
			cp += ev->vn_next;
		ev = (GElf_Verneed*)cp;

		liblist_t *veraux = NULL;
		if (!(veraux = liblist_alloc())) {
			liblist_free(deps);
			liblist_free(vers);
			elf_end(elf);
			return (NULL);
		}
		
		buf = cp;

		cp += ev->vn_aux;
		
		ea = NULL;
		for (a = 0; a < ev->vn_cnt; a++) {
			if (ea)
				cp += ea->vna_next;
			ea = (GElf_Vernaux*)cp;
			liblist_add(veraux, ea->vna_name);
		}

		liblist_add(vers, ev->vn_file);
		vers->tail->verlist = veraux;

		cp = buf;
	}

	/* Consolidate version and dependency information */
	liblist_foreach(deps, setver_liblist_cb, vers, NULL);
	liblist_free(vers);

	/*
	 * Now, figure out what versions we provide.
	 */
	GElf_Verdef *vd = NULL;
	GElf_Verdaux *va = NULL;
	liblist_t *verdef = NULL;
	
	if (!(verdef = liblist_alloc())) {
		liblist_free(deps);
		liblist_free(vers);
		elf_end(elf);
		return (NULL);
	}

	if (verdefnum > 0 && data_verdef) {
		buf = data_verdef->d_buf;
		cp = buf;
	}
	
	for (t=0; t < verdefnum; t++) {
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
			else
				liblist_add(verdef, va->vda_name);
		}

		cp = buf;
	}
	
	if (!(dyn = malloc(sizeof(dyninfo_t)))) {
		elf_end(elf);
		return (NULL);
	}

	dyn->runpath = runpath;
	dyn->dynstr = dynstr;
	dyn->elf = elf;
	dyn->deps = deps;
	dyn->def = def;
	dyn->vers = verdef;
	SHA1Final(dyn->hash, &shc);

	return (dyn);
}

void
dyninfo_free(dyninfo_t *dyn)
{
	if (dyn) {
		liblist_free(dyn->deps);
		elf_end(dyn->elf);
		free(dyn);
	}
}
