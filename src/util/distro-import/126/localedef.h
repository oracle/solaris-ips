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
 * Copyright 2009 Sun Microsystems, Inc.  All rights reserved.
 * Use is subject to license terms.
 */

/*
 * (c) Copyright 1990, 1991, 1992, 1993 OPEN SOFTWARE FOUNDATION, INC.
 * ALL RIGHTS RESERVED
 *
 * (C) COPYRIGHT International Business Machines Corp. 1991
 * All Rights Reserved
 */

#ifndef	_SYS_LOCALEDEF_H
#define	_SYS_LOCALEDEF_H

#ifdef __cplusplus
extern "C" {
#endif

/*
 * OSF/1 1.2
 */

/*
 * @(#)$RCSfile: localedef.h,v $ $Revision: 1.1.4.3 $ (OSF) $Date: 1992/09/10
 * 19:00:58 $
 */

/*
 * COMPONENT_NAME: (CMDLOC) Locale Database Commands
 *
 * 1.13  com/inc/sys/localedef.h, libcnls, bos320, 9132320 7/31/91 09:53:36
 */

/*
 * WARNING:
 * The interfaces defined in this header file are for Sun private use only.
 * The contents of this file are subject to change without notice for the
 * future releases.
 */

/*
 * Call the method named 'n' from the handle 'h'.
 *
 * METHOD() is used to invoke a user mode API method (i.e., either EUC
 * Process Code or Dense Process Code mode in 2.6)
 *
 * METHOD_NATVE() is used to explicitly invoke a native mode API method
 * (i.e., Dense Process Code mode in 2.6)
 */
#define	METHOD(h, n)		(*(h->core.user_api->n))
#define	METHOD_NATIVE(h, n)	(*(h->core.native_api->n))

/*
 * Forward define the major locale class objects before any
 * possible references
 */
typedef struct _LC_charmap_t 	_LC_charmap_t;
typedef struct _LC_monetary_t 	_LC_monetary_t;
typedef struct _LC_numeric_t	_LC_numeric_t;
typedef struct _LC_messages_t	_LC_messages_t;
typedef struct _LC_time_t	_LC_time_t;
typedef struct _LC_collate_t	_LC_collate_t;
typedef struct _LC_ctype_t	_LC_ctype_t;
typedef struct _LC_locale_t	_LC_locale_t;

#include <sys/lc_core.h>

#ifdef _LOCALEDEF
#define	_const		/* So localedef can assign into locale objects */
#else /* _LOCALEDEF */
#define	_const	const	/* Warn about any assignments */
#endif /* _LOCALEDEF */

/*
 * _LC_charmap_t
 *
 * Structure representing CHARMAP class which maps characters to process code
 * and vice-versa.
 */
typedef struct {
	char	euc_bytelen0,
		euc_bytelen1,	/* byte length of CS1 (eucw1) */
		euc_bytelen2,	/* byte length of CS2 (eucw2) */
		euc_bytelen3;	/* byte length of CS3 (eucw3) */
	char	euc_scrlen0,
		euc_scrlen1,	/* screen column len of CS1 (scrw1) */
		euc_scrlen2,	/* screen column len of CS2 (scrw2) */
		euc_scrlen3;	/* screen column len of CS3 (scrw3) */
	wchar_t	cs1_base;	/* CS1 dense code base value */
	wchar_t	cs2_base;	/* CS2 dense code base value */
	wchar_t	cs3_base;	/* CS3 dense code base value */
	wchar_t dense_end;	/* dense code last value */
	wchar_t cs1_adjustment;	/* CS1 adjustment value */
	wchar_t cs2_adjustment;	/* CS2 adjustment value */
	wchar_t cs3_adjustment;	/* CS3 adjustment value */
} _LC_euc_info_t;

typedef enum {
	_FC_EUC,		/* any EUC */
	_FC_UTF8,		/* UTF-8 */
	_FC_OTHER		/* anything else (SJIS, Big5, etc.) */
} _LC_fc_type_t;

typedef enum {
	_PC_EUC,		/* EUC Process Code */
	_PC_DENSE,		/* Dense Process Code */
	_PC_UCS4		/* ISO 10646 UCS4 */
} _LC_pc_type_t;

typedef struct {
	wchar_t	min;		/* min wchar of this chunk */
	wchar_t	max;		/* max wchar of this chunk */
} _LC_width_range_t;

typedef struct {
	unsigned char	width;		/* column width for this chunk */
	int	entries;	/* number of entries in this chunk */
	_const _LC_width_range_t	*ranges; /* range table */
} _LC_widthtabs_t;

struct _LC_charmap_t {
	_LC_core_charmap_t	core;

	_const char	*cm_csname;		/* codeset name  */

	_LC_fc_type_t	cm_fc_type;	/* file code type */
	_LC_pc_type_t	cm_pc_type;	/* process code type */

	size_t	cm_mb_cur_max;	/* max encoding length for this codeset  */
	size_t	cm_mb_cur_min;	/* min encoding length for this codeset  */

	unsigned char	cm_reserved;	/* reserved */
	unsigned char	cm_def_width;	/* default width */
	unsigned char	cm_base_max;	/* base area size: 0, 127, or 255 */
	unsigned char	cm_tbl_ent;	/* # of extended table entries */

	_LC_euc_info_t	*cm_eucinfo; 	/* pointer to EUC info table */

	_LC_widthtabs_t	*cm_tbl; 	/* width table */
};


/*
 * _LC_monetary_t
 *
 * Structure representing MONETARY class which defines the formatting
 * of monetary quantities for a locale.
 */
struct _LC_monetary_t {
	_LC_core_monetary_t	core;

	_const char	*int_curr_symbol; /* international currency symbol */
	_const char	*currency_symbol; /* national currency symbol */
	_const char	*mon_decimal_point; /* currency decimal point */
	_const char	*mon_thousands_sep; /* currency thousands separator */
	_const char	*mon_grouping;	/* currency digits grouping */
	_const char	*positive_sign;	/* currency plus sign */
	_const char	*negative_sign;	/* currency minus sign */
	char	int_frac_digits;	/* internat currency fract digits */
	char	frac_digits;		/* currency fractional digits */
	char	p_cs_precedes;		/* currency plus location */
	char	p_sep_by_space;		/* currency plus space ind. */
	char	n_cs_precedes;		/* currency minus location */
	char	n_sep_by_space;		/* currency minus space ind. */
	char	p_sign_posn;		/* currency plus position */
	char	n_sign_posn;		/* currency minus position */

	char	int_p_cs_precedes;	/* int'l currency plus location */
	char	int_p_sep_by_space;	/* int'l currency plus space ind. */
	char	int_n_cs_precedes;	/* int'l currency minus location */
	char	int_n_sep_by_space;	/* int'l currency minus space ind. */
	char	int_p_sign_posn;	/* int'l currency plus position */
	char	int_n_sign_posn;	/* int'l currency minus position */

};


/*
 * _LC_numeric_t
 *
 * Structure representing NUMERIC class which defines the formatting
 * of numeric quantities in a locale.
 */
struct _LC_numeric_t {
	_LC_core_numeric_t	core;

	/* Types of the following should be clarified later */
	_const char	*decimal_point;
	_const char	*thousands_sep;
	_const char	*grouping;
};


/*
 * _LC_messages_t
 *
 * Structure representing MESSAGES class which defines the content
 * of affirmative versus negative responses in a locale.
 */
struct _LC_messages_t  {
	_LC_core_messages_t	core;

	_const char	*yesexpr; /* POSIX: Expression for affirmative. */
	_const char	*noexpr;  /* POSIX: Expression for negative. */
	_const char	*yesstr;  /* X/OPEN: colon sep str for affirmative. */
	_const char	*nostr;   /* X/OPEN: colon sep str for negative. */
};


/*
 * _LC_time_t
 *
 * Structure representing the TIME class which defines the formatting
 * of time and date quantities in this locale.
 */
struct _LC_time_t {
	_LC_core_time_t	core;

	_const char	*d_fmt;
	_const char	*t_fmt;
	_const char	*d_t_fmt;
	_const char	*t_fmt_ampm;
	_const char	*abday[7];
	_const char	*day[7];
	_const char	*abmon[12];
	_const char	*mon[12];
	_const char	*am_pm[2];
	_const char	**era;		/* NULL terminated array of strings */
	_const char	*era_d_fmt;
	_const char	*alt_digits;
	_const char	*era_d_t_fmt;
	_const char	*era_t_fmt;
	_const char	*date_fmt;	/* Solaris specific */
};


/*
 * _LC_weight_t
 */

typedef wchar_t *_LC_weight_t;


/*
 * _LC_collel_t
 *
 * Collation data for a collation symbol
 */
typedef struct {
	_const char	*ce_sym; 	/* value of collation symbol */
	_LC_weight_t	ce_wgt; 	/* The weights associated with a */
					/* collating symbol matching ce_sym */
} _LC_collel_t;

/*
 * _LC_subs_t
 *
 * Substring source and target pair
 */
typedef struct {
	_LC_weight_t	ss_act;
		/* indicates for which orders this */
		/* susbstitution string is active. */
	_const char	*ss_src;	/* source string to match */
	_const char	*ss_tgt;	/* target string to replace */
} _LC_subs_t;

/*
 * _LC_exsubs_t
 *
 * Extended substring/substitue information
 */
typedef struct {
	unsigned int	ess_order;	/* order applies */
	unsigned int	ess_srclen;	/* length of source string */
	union {
		_const char *sp;
		_const wchar_t *wp;
	} ess_src;
	union {
		unsigned int wgtidx;	/* index to ext_wgtstr */
		wchar_t	*wgtstr;	/* pointer to weight str */
	} ess_wgt;
} _LC_exsubs_t;

/*
 * _LC_collextinfo_t
 *
 * Extended informatin.
 */
typedef struct {
	size_t		ext_wgtstrsz;	/* size of wgt string table */
	_const wchar_t	*ext_wgtstr;	/* weight string table */
	_const char	*ext_submap;	/* quick lookup table */
	size_t		ext_nsubs;	/* number of subs table */
	_const _LC_exsubs_t *ext_hsubs;	 /* subs pair */
	_const _LC_exsubs_t *ext_hwsubs; /* subs pair (wchar) */
	_const unsigned int *ext_hsuboff; /* table offset for each order */
	_const unsigned int *ext_hsubsz;  /* table size for each order */
	wchar_t		ext_col_max;	/* max coll weight (non-relative) */
	unsigned int	ext_rsvd[15];	/* reserved for future use */
} _LC_collextinfo_t;

/*
 * _LC_collate_t
 *
 * Structure representing COLLATE class defining the collation rules
 * for a locale.
 */
struct _LC_collate_t {
	_LC_core_collate_t	core;

	_LC_charmap_t	*cmapp; 	/* pointer to charmap object */
	unsigned char	co_nord; 	/* number of collation orders */
					/* supported in this locale */
	unsigned char	co_r_order;	/* relative weight flag */
	unsigned char	co_ext;		/* extinfo flag */
#ifdef	_LP64
	unsigned char	__filler1[5];
#else
	unsigned char	__filler1[1];
#endif

	_LC_weight_t	co_sort;	/* sort order */
					/* processing flags */

	wchar_t	co_wc_min;		/* min process code */
	wchar_t	co_wc_max;		/* max process code */
	wchar_t	co_hbound;		/* max process code with */
					/* "unique" info */

	wchar_t	co_col_min;		/* min unique coll weight */
	wchar_t	co_col_max;		/* max unique coll weight */

	_const _LC_weight_t	*co_coltbl;
					/* array of collation weights */
	_const _LC_collel_t	**co_cetbl;
					/* array of collating elements */

	unsigned char	co_nsubs;	/* number of sub strs  */
	_const _LC_subs_t	*co_subs;	/* substitution strs   */
	_const void	*co_extinfo;	/* extended info */
};

/*
 * MASKS for the co_colmod[] sort modifier array
 */
#define	_COLL_FORWARD_MASK	0x0001
#define	_COLL_BACKWARD_MASK	0x0002
#define	_COLL_NOSUBS_MASK	0x0004
#define	_COLL_POSITION_MASK	0x0008
#define	_COLL_SUBS_MASK		0x0010
#define	_COLL_WGT_WIDTH1	0x0100
#define	_COLL_WGT_WIDTH2	0x0200
#define	_COLL_WGT_WIDTH3	0x0400
#define	_COLL_WGT_WIDTH4	0x0800
#define	_COLL_WGT_MASK		0x0f00

/*
 * MASKS for the ss_act[] flags
 */
#define	_SUBS_ACTIVE	0x01
#define	_SUBS_REGEXP	0x02

/*
 * _LC_classnm_t
 *
 * Element mapping class name to a bit-unique mask.
 */
typedef struct {
	_const char	*name;
	unsigned int	mask;
} _LC_classnm_t;


/*
 * _LC_ctype_t
 *
 * Structure representing CTYPE class which defines character
 * membership in a character class.
 */

/*
 * User defined transformation name table
 */
typedef struct {
	_const char		*name;	/* name of the transformation */
	unsigned int	index;	/* index value to transtab table */
	wchar_t		tmin;	/* minimum code for transformation */
	wchar_t		tmax;	/* maximum code for transformation */
} _LC_transnm_t;

typedef struct __LC_transtabs_t {
	_const wchar_t	*table;	/* transformation table */
	wchar_t	tmin;		/* minimum code for sub-transformation */
	wchar_t	tmax;		/* maximum code for sub-transformation */
	struct __LC_transtabs_t	*next;	/* link to next sub-transformation */
} _LC_transtabs_t;


/*
 * LcBind tables to bind a name and a typed value
 */
typedef enum {
	_LC_TAG_UNDEF,		/* undefined */
	_LC_TAG_TRANS,		/* transformation */
	_LC_TAG_CCLASS		/* character class */
} _LC_bind_tag_t;

typedef void *_LC_bind_value_t;	/* data type for any value */

typedef struct {
	_const char	*bindname;		/* LCBIND name */
	_LC_bind_tag_t	bindtag; 	/* tag (data type) */
	_LC_bind_value_t bindvalue; 	/* value */
} _LC_bind_table_t;

struct _LC_ctype_t {
	_LC_core_ctype_t	core;

	_LC_charmap_t	*cmapp; 	/* pointer to charmap object */

	/* min and max process code */
	wchar_t	min_wc;
	wchar_t	max_wc;

	wchar_t	max_upper;		/* Last character with */
					/* upper-case equiv */
	wchar_t	max_lower;		/* Last character with */
					/* lower-case equiv */

	/* upper, lower translation */
	_const wchar_t	*upper;		/* [0..max_upper] */
	_const wchar_t	*lower;		/* [0..max_lower] */

	/* character class membership */
	_const unsigned int	*mask;	/* Array of masks for CPs 0..255 */
	_const unsigned int	*qmask;	/* Array of masks for CPs 255..+ */
	_const unsigned char	*qidx;	/* index into qmask for */
					/* CPs 255..+ */

	wchar_t	qidx_hbound;		/* Last code-point with unique */
					/* qidx value */
	/* class name mapping */
	int		nbinds;		/* no of lcbind entries */
	_LC_bind_table_t *bindtab;	/* pointer to lcbind table */

	/* trans name mapping */
	int		ntrans;		/* no. of transtab array elements */
	_LC_transnm_t	*transname; 	/* pointer to trans name tables */
	_const _LC_transtabs_t	*transtabs; /* pointer to transtabs array */

	/* For _ctype[] link */
	/* size of _ctype[] */
	size_t  ctypesize;
	/* pointer to _ctype[] of this locale */
	_const unsigned char	*ctypedata;
	/* reserved for future extension */
	void	*reserved[8];
};


/*
 * _LC_locale_t
 *
 * Entry point to locale database.  setlocale() receives a pointer to
 * this structure from __lc_load().
 */

/*
 * IF THIS NUMBER CHANGES, IT MUST ALSO BE CHANGED IN
 * langinfo.h
 */
#ifndef _NL_NUM_ITEMS
#define	_NL_NUM_ITEMS	59		/* 58 + 1 */
#endif

struct _LC_locale_t {
	_LC_core_locale_t	core;

	struct lconv	*nl_lconv;

	_LC_charmap_t	*lc_charmap;
	_LC_collate_t	*lc_collate;
	_LC_ctype_t	*lc_ctype;
	_LC_monetary_t	*lc_monetary;
	_LC_numeric_t	*lc_numeric;
	_LC_messages_t	*lc_messages;
	_LC_time_t	*lc_time;

	/* to be used for specifying the size of nl_info */
	int	no_of_items;
	char	*nl_info[_NL_NUM_ITEMS];
};

#define	_LC_MAX_OBJECTS	256

extern _LC_charmap_t	*__lc_charmap;
extern _LC_collate_t	*__lc_collate;
extern _LC_ctype_t	*__lc_ctype;
extern _LC_monetary_t	*__lc_monetary;
extern _LC_numeric_t	*__lc_numeric;
extern _LC_messages_t	*__lc_messages;
extern _LC_time_t	*__lc_time;
extern _LC_locale_t	*__lc_locale;

#ifdef __cplusplus
}
#endif

#endif	/* _SYS_LOCALEDEF_H */
