#include <stdlib.h>
#include <stdio.h>
#include "liblist.h"

liblist_t *
liblist_alloc()
{
	liblist_t *n;

	if(!(n = malloc(sizeof(liblist_t))))
		return (NULL);
	
	n->head = NULL;
	n->tail = NULL;

	return (n);
}

void
liblist_free(liblist_t *lst)
{
	if (!lst)
		return;
	
	libnode_t *n = lst->head;
	libnode_t *temp = NULL;
	
	while (n) {
		liblist_free(n->verlist);
		temp = n;
		n = n->next;
		free(temp);
	}

	free(lst);
}

libnode_t *
liblist_add(liblist_t *lst, off_t off)
{
	libnode_t *n = NULL;

	if (!lst)
		return (NULL);

	if(!(n = malloc(sizeof(libnode_t))))
		return (NULL);
	
	n->nameoff = off;
	n->verlist = NULL;
	n->next = NULL;
	
	if (!lst->head) {
		lst->head = n;
		lst->tail = n;
	}
	else {
		lst->tail->next = n;
		lst->tail = n;
	}

	return (n);
}

void
liblist_foreach(liblist_t *lst, void (*cb)(libnode_t *, void *, void *),
    void *info, void *info2)
{
	if (!lst)
		return;

	libnode_t *n = lst->head;

	while (n) {
		cb(n, info, info2);
		n = n->next;
	}
}

liblist_t *
liblist_copy(liblist_t *lst)
{
	if (!lst)
		return (NULL);
	
	liblist_t *nl = NULL;

	if (!(nl = liblist_alloc()))
		return (NULL);
	
	liblist_foreach(lst, copyto_liblist_cb, nl, NULL);

	return nl;
}


/* callbacks */
void
print_liblist_cb(libnode_t *n, void *info, void *info2)
{
	char *st = (char*)info;
	printf("%s\n", (char*) (st + n->nameoff), n->verlist);
	liblist_foreach(n->verlist, print_liblist_cb, info, NULL);
}

void
setver_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *vers = (liblist_t*)info;

	libnode_t *vn = vers->head;

	while (vn) {
		if (vn->nameoff == n->nameoff) {
			n->verlist = liblist_copy(vn->verlist);
			break;
		}
		vn = vn->next;
	}
}

void
copyto_liblist_cb(libnode_t *n, void *info, void *info2)
{
	liblist_t *lst = (liblist_t*)info;
	liblist_add(lst, n->nameoff);
	lst->tail->verlist = liblist_copy(n->verlist);
}

