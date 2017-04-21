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

/* DirAction to deliver a directory action. */
public class DirAction {
        private String filemode;
        private String username;
        private String groupname;
        private String destpath;

        /* Constructor for DirAction. */
        public DirAction(String fm, String un, String gn,
            String dp){
                filemode = fm;
                username = un;
                groupname = gn;
                destpath = dp;
        }

        /** method to get file mode.
         * @return String file mode.
         */
        public String getFilemode(){
                return filemode;
        }

        /** method to get user name.
         * @return String user name.
         */
        public String getUsername(){
                return username;
        }

        /** method to get group name.
         * @return String group name.
         */
        public String getGroupname(){
                return groupname;
        }

        /** method to get destination path.
         * @return String destination path.
         */
        public String getDestpath(){
                return destpath;
        }

        /** 
         * Method to set file mode.
         * @param fm   String file mode.
         * @return  Nothing.
         */
        public void setFilemode(String fm){
                filemode = fm;
        }
        /** 
         * Method to set user name.
         * @param un   String user name.
         * @return  Nothing.
         */
        public void setUsername(String un){
                username = un;
        }
        /** 
         * Method to set group name.
         * @param gp   String group name.
         * @return  Nothing.
         */
        public void setGroupname(String gp){
                groupname = gp;
        }
        /** 
         * Method to set destination path.
         * @param dp   String destination path.
         * @return  Nothing.
         */
        public void setDestpath(String dp){
                destpath  = dp;
        }
}

