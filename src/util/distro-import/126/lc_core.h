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
 * Copyright 2004 Sun Microsystems, Inc.  All rights reserved.
 * Use is subject to license terms.
 */

/*
 * (c) Copyright 1990, 1991, 1992, 1993 OPEN SOFTWARE FOUNDATION, INC.
 * ALL RIGHTS RESERVED
 *
 * (C) COPYRIGHT International Business Machines Corp. 1985, 1989
 * All Rights Reserved
 */

#ifndef	_SYS_LC_CORE_H
#define	_SYS_LC_CORE_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * OSF/1 1.2
 */

/*
 * @(#)$RCSfile: lc_core.h,v $ $Revision: 1.1.2.9 $ (OSF) $Date: 1992/03/26
 * 23:05:55 $
 */

/*
 * 1.6  com/inc/sys/lc_core.h, libccnv, bos320, 9132320m 8/11/91 14:14:46
 *
 * COMPONENT_NAME: (LIBCLOC) Locale Related Data Structures and API
 */

/*
 * WARNING:
 * The interfaces defined in this header file are for Sun private use only.
 * The contents of this file are subject to change without notice for the
 * future releases.
 */

#include <stddef.h>
#include <nl_types.h>
#include <sys/types.h>
#include <regex.h>
#include <stdarg.h>
#include <wchar.h>
#include <wctype.h>

#ifndef FALSE
#define	FALSE	(0)
#endif

#ifndef TRUE
#define	TRUE	(1)
#endif

/*
 * In OSF/1, method elements in the structures point to functions
 */


/*
 * Valid type ids for NLS objects
 */
typedef enum __lc_type_id_t {
	_LC_CAR = 1,
	_LC_LOCALE = 2,
	_LC_CHARMAP = 3,
	_LC_CTYPE = 4,
	_LC_COLLATE = 5,
	_LC_NUMERIC = 6,
	_LC_MONETARY = 7,
	_LC_TIME = 8,
	_LC_MESSAGES = 9
} __lc_type_id_t;


typedef struct {
	__lc_type_id_t	type_id;
	unsigned int	magic;
	unsigned short	major_ver;
	unsigned short	minor_ver;
	size_t	size;
} _LC_object_t;

/*
 * Object magic
 */
#define	_LC_MAGIC	0x05F1

/*
 * Version.  Anytime the data structures in localedef or lc_core change
 *	in an incompatible way, this number should change
 */

#define	_LC_VERSION_MAJOR	3
#define	_LC_VERSION_MINOR	0

/*
 * Methods structure - can be used interchangeably with each
 * _LC_methods_<category>_t.
 */

typedef void (*_LC_methods_func_t)(void);

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */
	_LC_methods_func_t methods[1];
} _LC_methods_t;

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* locale info method */
	char	*(*nl_langinfo)(_LC_charmap_t *, nl_item);

	/* Process code conversion methods */
	int	(*mbtowc)(_LC_charmap_t *, wchar_t *, const char *,
		size_t);
	size_t	(*mbstowcs)(_LC_charmap_t *, wchar_t *, const char *,
		size_t);
	int	(*wctomb)(_LC_charmap_t *, char *, wchar_t);
	size_t	(*wcstombs)(_LC_charmap_t *, char *, const wchar_t *,
		size_t);

	/* Character encoding length method */
	int	(*mblen)(_LC_charmap_t *, const char *, size_t);

	/* Character display width methods */
	int	(*wcswidth)(_LC_charmap_t *, const wchar_t *, size_t);
	int	(*wcwidth)(_LC_charmap_t *, wchar_t);

	/* Solaris internal API */
	int	(*mbftowc)(_LC_charmap_t *, char *, wchar_t *,
		int (*)(void), int *);

	wint_t	(*fgetwc)(_LC_charmap_t *, FILE *);

	/* MSE extension */
	wint_t	(*btowc)(_LC_charmap_t *, int);
	int		(*wctob)(_LC_charmap_t *, wint_t);
	int		(*mbsinit)(_LC_charmap_t *, const mbstate_t *);
	size_t	(*mbrlen)(_LC_charmap_t *, const char *, size_t, mbstate_t *);
	size_t	(*mbrtowc)(_LC_charmap_t *, wchar_t *, const char *,
		size_t, mbstate_t *);
	size_t	(*wcrtomb)(_LC_charmap_t *, char *, wchar_t, mbstate_t *);
	size_t	(*mbsrtowcs)(_LC_charmap_t *, wchar_t *, const char **,
		size_t, mbstate_t *);
	size_t	(*wcsrtombs)(_LC_charmap_t *, char *, const wchar_t **,
		size_t, mbstate_t *);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_charmap_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_charmap_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_charmap_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_charmap_t	*native_api;

	/*
	 * process code to process code conversion methods
	 */
	wchar_t	(*__eucpctowc)(_LC_charmap_t *, wchar_t);
	wchar_t	(*__wctoeucpc)(_LC_charmap_t *, wchar_t);
	void	*data;
} _LC_core_charmap_t;

/*
 * Process code to process code conversion macros
 * Note that `wc' is evalucated twice at run-time. _eucpctowc(*ws++) must
 * be avoided.
 */
#define	_eucpctowc(h, wc)	\
	((((uint32_t)wc) <= 0x9f) ? (wc) : (*(h->core.__eucpctowc))(h, (wc)))
#define	_wctoeucpc(h, wc)	\
	((((uint32_t)wc) <= 0x9f) ? (wc) : (*(h->core.__wctoeucpc))(h, (wc)))

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* classification methods */
	wctype_t (*wctype)(_LC_ctype_t *, const char *);
	int	(*iswctype)(_LC_ctype_t *, wchar_t, wctype_t);

	/* case conversion methods */
	wint_t	  (*towupper)(_LC_ctype_t *, wint_t);
	wint_t	  (*towlower)(_LC_ctype_t *, wint_t);
	wchar_t	  (*_trwctype)(_LC_ctype_t *, wchar_t, int);
	wctrans_t (*wctrans)(_LC_ctype_t *, const char *);
	wint_t    (*towctrans)(_LC_ctype_t *, wint_t, wctrans_t);

	_LC_methods_func_t placeholders[5]; /* reserved for future extension */
} _LC_methods_ctype_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_ctype_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_ctype_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_ctype_t	*native_api;
	void	*data;
} _LC_core_ctype_t;

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* character collation methods */
	int	(*strcoll)(_LC_collate_t *, const char *,
		const char *);
	size_t	(*strxfrm)(_LC_collate_t *, char *, const char *,
		size_t);

	/* process code collation methods */
	int	(*wcscoll)(_LC_collate_t *, const wchar_t *,
		const wchar_t *);
    size_t	(*wcsxfrm)(_LC_collate_t *, wchar_t *, const wchar_t *,
		size_t);

	/* filename matching methods */
	int	(*fnmatch)(_LC_collate_t *, const char *, const char *,
		const char *, int);

	/* regular expression methods */
	int	(*regcomp)(_LC_collate_t *, regex_t *, const char *,
		int);
	size_t	(*regerror)(_LC_collate_t *, int, const regex_t *,
		char *, size_t);
	int	(*regexec)(_LC_collate_t *, const regex_t *, const char *,
		size_t,	regmatch_t *, int);
	void	(*regfree)(_LC_collate_t *, regex_t *);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_collate_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_collate_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_collate_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_collate_t	*native_api;
	void	*data;
} _LC_core_collate_t;


struct tm;
typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* time info method */
	char	*(*nl_langinfo)(_LC_time_t *, nl_item);

	/* time character string formatting methods */
	size_t	(*strftime)(_LC_time_t *, char *, size_t, const char *,
		const struct tm *);
	char	*(*strptime)(_LC_time_t *, const char *, const char *,
		struct tm *);
	struct tm	*(*getdate)(_LC_time_t *, const char *);

	/* time process code string formatting methods */
	size_t	(*wcsftime)(_LC_time_t *, wchar_t *, size_t,
		const char *, const struct tm *);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_time_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_time_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_time_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_time_t	*native_api;
	void	*data;
} _LC_core_time_t;

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* monetary info method */
	char	*(*nl_langinfo)(_LC_monetary_t *, nl_item);

	/* character string monetary formatting method */
	ssize_t	(*strfmon)(_LC_monetary_t *, char *, size_t,
		const char *, va_list);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_monetary_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_monetary_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_monetary_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_monetary_t	*native_api;
	void	*data;
} _LC_core_monetary_t;


typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* langinfo method */
	char	*(*nl_langinfo)(_LC_numeric_t *, nl_item);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_numeric_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_numeric_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_numeric_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_numeric_t	*native_api;
	void	*data;
} _LC_core_numeric_t;

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* langinfo method */
	char	*(*nl_langinfo)(_LC_messages_t *, nl_item);

	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_messages_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_messages_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_messages_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_messages_t	*native_api;
	void	*data;
} _LC_core_messages_t;

typedef struct {
	short	nmethods;	/* no of methods array elements */
	short	ndefined;	/* no of methods defined in this object */

	/* langinfo method */
	char	*(*nl_langinfo)(_LC_locale_t *, nl_item);
	struct lconv	*(*localeconv)(_LC_locale_t *);
	/* reserved for future extension */
	_LC_methods_func_t	placeholders[5];
} _LC_methods_locale_t;

typedef struct {
	_LC_object_t	hdr;

	_LC_locale_t	*(*init)(_LC_locale_t *);
	int		(*destructor)(_LC_locale_t *);

	/* pointer to user API methods */
	_LC_methods_locale_t	*user_api;

	/* pointer to native API methods */
	_LC_methods_locale_t	*native_api;
	void	*data;
} _LC_core_locale_t;


extern char	__mbst_get_nconsumed(const mbstate_t *);
extern void	__mbst_set_nconsumed(mbstate_t *, char);
extern int	__mbst_get_consumed_array(const mbstate_t *, char *,
	size_t, size_t);
extern int	__mbst_set_consumed_array(mbstate_t *, const char *,
	size_t, size_t);
extern void *__mbst_get_locale(const mbstate_t *);
extern void	__mbst_set_locale(mbstate_t *, const void *);
extern void	__fseterror_u(FILE *);

#ifdef __cplusplus
}
#endif

#endif	/* _SYS_LC_CORE_H */
