#ifndef __ELFEXTRACT_H__
#define __ELFEXTRACT_H__

#include <sys/types.h>
#include "liblist.h"

#ifndef MIN
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#endif

typedef struct dyninfo {
	off_t		runpath;	/* offset in *st of the runpath */
	char		*st;		/* string table			*/
	liblist_t 	*deps;		/* dependency list (also contains */
					/* 	offsets in *st)		*/
	unsigned char	hash[20];	/* SHA1 Hash of significant segs. */
} dyninfo_t;

char *getident(int fd);
int iself(int fd);
int iself32(int fd);
Elf32_Ehdr *gethead32(int fd);
Elf64_Ehdr *gethead64(int fd);
dyninfo_t *getdynamic32(int fd);
dyninfo_t *getdynamic64(int fd);

#endif
