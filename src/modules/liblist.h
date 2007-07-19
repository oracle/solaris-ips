#ifndef __LIBLIST_H__
#define __LIBLIST_H__

#include <sys/types.h>

struct libnode;
struct liblist;

typedef struct libnode {
	off_t		nameoff;	/* offset of name of this node in */
					/* a particular name table 	  */
	struct liblist	*verlist;	/* version string list head	  */
	struct libnode	*next;		/* next node			  */
} libnode_t;

typedef struct liblist {
	libnode_t	*head;
	libnode_t	*tail;
} liblist_t;


/* liblist utils */
liblist_t *liblist_alloc();
void liblist_free(liblist_t *lst);
libnode_t *liblist_add(liblist_t *lst, off_t off);
void liblist_foreach(liblist_t *lst, void (*cb)(libnode_t *, void *, void *), 
    void *info, void *info2);
liblist_t *liblist_copy(liblist_t *lst);

/* callbacks */
void print_liblist_cb(libnode_t *n, void *info, void *info2);
void setver_liblist_cb(libnode_t *n, void *info, void *info2);
void copyto_liblist_cb(libnode_t *n, void *info, void *info2);

#endif
