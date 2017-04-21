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
 *
 *
 *
 * Copyright (c) 2015, 2017, Oracle and/or its affiliates. All rights reserved.
 */

package com.oracle.ips;
/** Deliver link action. */
public class LinkAction {
        private String path;
        private String target;

        /**
         * Constructor for link action.
         * @param pt    path name.
         * @param tgt   target name.
         */
        public LinkAction(String pt, String tgt){
                path = pt;
                target = tgt;
        }

        /** method to get path.
         * @return String path.
         */
        public String getPath(){
                return path;
        }

        /** method to get target.
         * @return String target.
         */
        public String getTarget(){
                return target;
        }
        /**
         * Method to set path
         * @param pt    String path.
         */
        public void setPath(String pt){
                path = pt;
        }
        /**
         * Method to set target.
         * @param tgt   String target.
         */
        public void setTarget(String tgt){
                target = tgt;
        }
}
