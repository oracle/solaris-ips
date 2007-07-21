#ifndef __ELFEXTRACT_H__
#define __ELFEXTRACT_H__

#include <sys/types.h>
#include "liblist.h"

#ifndef MIN
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#endif

typedef struct dyninfo {
	off_t		runpath;	/* offset in table of the runpath */
	off_t		dynstr;		/* string table			  */
	liblist_t 	*deps;		/* dependency list (also contains */
					/* 	offsets)		  */
	liblist_t 	*defs;		/* version provided list (also	  */
					/* 	contains offsets)	  */
	unsigned char	hash[20];	/* SHA1 Hash of significant segs. */
	Elf		*elf;		/* elf data -- must be freed	  */
} dyninfo_t;

typedef struct hdrinfo {
	int type;			/* e_type		*/
	int bits;			/* 32/64		*/
	int arch;			/* e_machine		*/
	int data;			/* e_ident[EI_DATA]	*/
	int osabi;			/* e_ident[EI_OSABI]	*/
} hdrinfo_t;

char *getident(int fd);
int iself(int fd);
int iself32(int fd);
dyninfo_t *getdynamic(int fd);
void dyninfo_free(dyninfo_t *dyn);
hdrinfo_t *getheaderinfo(int fd);

char *pkg_string_from_type(int type);
char *pkg_string_from_arch(int arch);
char *pkg_string_from_data(int data);
char *pkg_string_from_osabi(int osabi);

#endif
