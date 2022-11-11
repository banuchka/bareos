#!/usr/bin/env python
# -*- coding: utf-8 -*-

from bareosfd import *
import os
from subprocess import *
from BareosFdPluginBaseclass import *
import BareosFdWrapper
import datetime
import time
import tempfile
import shutil
import json

class BareosFdLibvirt(BareosFdPluginBaseclass):
    """
        Plugin for backing up all mysql innodb databases found in a specific mysql server
        using the Percona xtrabackup tool.
    """

    def __init__(self, plugindef):
        # BareosFdPluginBaseclass.__init__(self, plugindef)
        super(BareosFdLibvirt, self).__init__(plugindef)
        # we first create and backup the stream and after that
        # the lsn file as restore-object
        self.files_to_backup = None
        self.logdir = "/var/log/bareos/"
        self.log = "bareos-plugin-libvirt.log"
        self.rop_data = {}
        self.max_to_lsn = 0
        self.err_fd = None

    def parse_plugin_definition(self, plugindef):
        """
        We have default options that should work out of the box in the most  use cases
        that the mysql/mariadb is on the same host and can be accessed without user/password information,
        e.g. with a valid my.cnf for user root.
        """
        BareosFdPluginBaseclass.parse_plugin_definition(self, plugindef)

        if "dumpbinary" in self.options:
            self.dumpbinary = self.options["dumpbinary"]
        else:
            self.dumpbinary = "xtrabackup"

        if "restorecommand" not in self.options:
            self.restorecommand = "cat - > file.img "
        else:
            self.restorecommand = self.options["restorecommand"]

        # Default is not to write an extra logfile
        #self.options['log'] = 'bareos-plugin-libvirt.log'
        if "log" not in self.options:
            self.log = False
        elif self.options["log"] == "false":
            self.log = False
        elif os.path.isabs(self.options["log"]):
            self.log = self.options["log"]
        else:
            self.log = os.path.join(self.logdir, self.options["log"])

        # By default, standard mysql-config files will be used, set
        # this option to use extra files
        self.connect_options = {"read_default_group": "client"}

        # If true, incremental jobs will only be performed, if LSN has increased
        # since last call.
        if (
            "strictIncremental" in self.options
            and self.options["strictIncremental"] == "true"
        ):
            self.strictIncremental = True
        else:
            self.strictIncremental = False

        if "vmname" in self.options:
            self.vmname = self.options["vmname"]
            self.tempdir = "/local/libvirt/backup/%s" % self.vmname
            if not os.path.exists(self.tempdir):
              os.makedirs(self.tempdir)
        else:
            self.vmname = ''

        return bRC_OK

    def check_plugin_options(self, mandatory_options=None):
        accurate_enabled = GetValue(bVarAccurate)
        if accurate_enabled is not None and accurate_enabled != 0:
            JobMessage(
                M_FATAL,
                "start_backup_job: Accurate backup not allowed please disable in Job\n",
            )
            return bRC_Error
        else:
            return bRC_OK

    def create_file(self, restorepkt):
        """
        On restore we create a subdirectory for the first base backup and each incremental backup.
        Because percona expects an empty directory, we create a tree starting with jobId/ of restore job
        """
        FNAME = restorepkt.ofname
        DebugMessage(100, "create file with %s called\n" % FNAME)
        self.writeDir = "%s/%d/" % (os.path.dirname(FNAME), self.jobId)
        # FNAME contains originating jobId after last .
        origJobId = int(FNAME.rpartition(".")[-1])
        DebugMessage(100, "Restore: '" + str(self.rop_data[origJobId][-1]) + "'\n")

        # Create restore directory, if not existent
        if not os.path.exists(self.writeDir):
            bareosfd.DebugMessage(
                200,
                "Directory %s does not exist, creating it now\n" % self.writeDir,
            )
            os.makedirs(self.writeDir)
        restoreFileName = os.path.basename(FNAME).rsplit('.',1)[0]
        DebugMessage(100, "Restore file Name: %s \n" % str(restoreFileName))
        restoreFileNumberArr = self.rop_data[origJobId][-1].split('.')
        DebugMessage(100, "Restore file Name: %s \n" % str(len(restoreFileNumberArr)))
        DebugMessage(100, "Restore file Name: %s \n" % str(restoreFileNumberArr))

        DebugMessage(100, "Restore: cat - > %s%s \n" % (self.writeDir, restoreFileName))
        self.restorecommand = 'cat - > %s%s' % (self.writeDir, restoreFileName)
        if os.path.exists('%s/%s.cpt' % (self.tempdir, self.vmname)):
            shutil.copyfile('%s/%s.cpt' % (self.tempdir, self.vmname), '%s/%s.cpt' % (self.writeDir,self.vmname)) 
        DebugMessage(
            100,
            'Restore using xbstream to extract files with "%s"\n' % self.restorecommand,
        )
        restorepkt.create_status = CF_EXTRACT
        return bRC_OK

    def start_backup_job(self):
        """
        We will check, if database has changed since last backup
        in the incremental case
        """
        check_option_bRC = self.check_plugin_options()
        if check_option_bRC != bRC_OK:
            return check_option_bRC
        bareosfd.DebugMessage(
            100, "start_backup_job, level: %s\n" % chr(self.level)
        )
        if chr(self.level) == "I":
            # We check, if we have a LSN received by restore object from previous job
            if self.max_to_lsn == 0:
                JobMessage(
                    M_FATAL,
                    "No LSN received to be used with incremental backup\n",
                )
                return bRC_Error
            else:
                last_lsn = self.max_to_lsn+1
            JobMessage(
                M_INFO, "Backup until LSN: %d\n" % last_lsn
            )
            if (
                self.max_to_lsn > 0
                and self.max_to_lsn >= last_lsn
                and self.strictIncremental
            ):
                bareosfd.DebugMessage(
                    100,
                    "Last LSN of DB %d is not higher than LSN from previous job %d. Skipping this incremental backup\n"
                    % (last_lsn, self.max_to_lsn),
                )
                self.files_to_backup = ["lsn_only"]
                return bRC_OK
        return bRC_OK

    def start_backup_file(self, savepkt):
        """
        This method is called, when Bareos is ready to start backup a file
        """
        if chr(self.level) == 'I':
            backupLevel = 'inc'
        else:
            backupLevel = 'full'

        if not self.files_to_backup:
            self.files_to_backup = ["drives", "xmlfile", "lsnfile"]

        self.file_to_backup = self.files_to_backup.pop(0)
        statp = StatPacket()
        savepkt.statp = statp

        if self.file_to_backup not in ["lsnfile", "xmlfile"]:
            #disk = self.file_to_backup

            # This is the database backup as xbstream
            savepkt.fname = "/_libvirt/%s.%s.zip.%010d" % (self.vmname, backupLevel, self.jobId)
            savepkt.type = FT_REG
#            if self.max_to_lsn > 0:
#                self.dumpcommand = 'python3 /home/banuchka/virtnbdbackup/virtnbdbackup -d centos1 -l inc -o - --transport unix -i %s --getdata --tempdir %s' % (disk, self.tempdir)
#            else:
#                self.dumpcommand = 'python3 /home/banuchka/virtnbdbackup/virtnbdbackup -d centos1 -l full -o - --transport unix -i %s --getdata --tempdir %s' % (disk, self.tempdir)
            self.dumpcommand = '/usr/bin/virtnbdbackup -n -d %s -l %s -o - -S %s' % (self.vmname, backupLevel, self.tempdir)
            DebugMessage(100, "Dumper: '" + self.dumpcommand + "'\n")
        elif self.file_to_backup == "xmlfile":
            # This is the database backup as xbstream
            savepkt.fname = "/_libvirt/%s.vmconfig.virtnbdbackup.%s.xml.%010d" % (self.vmname, self.max_to_lsn, self.jobId)
#            if self.max_to_lsn == 0:
#                savepkt.fname = "/_libvirt/%s.vmconfig.virtnbdbackup.xml.%010d" % (self.vmname, self.jobId)
#            else:
#                savepkt.fname = "/_libvirt/%s.vmconfig.virtnbdbackup.%s.xml.%010d" % (self.vmname, self.max_to_lsn, self.jobId)

            savepkt.type = FT_REG
            #vmconfig.virtnbdbackup.3.xml
            self.dumpcommand = "cat %s/vmconfig.virtnbdbackup.%s.xml" % (self.tempdir, self.max_to_lsn)
        elif self.file_to_backup == "lsnfile":
            startBackupCommand = 'cat %s/%s.cpt' % (self.tempdir, self.vmname)
            DebugMessage(100, "Running with %s" % startBackupCommand)
            startBackup = Popen(startBackupCommand, shell=True, stdout=None, stderr=self.err_fd)
            self.subprocess_returnCode = startBackup.wait()
            DebugMessage(100, "Start backup job with code: %s\n" % self.subprocess_returnCode)
            # The restore object containing the log sequence number (lsn)
            # Read checkpoints and create restore object
            checkpoints = ''
            # improve: Error handling
            with open("%s/%s.cpt" % (self.tempdir, self.vmname)) as lsnfile:
                for line in lsnfile:
                    key, value = line.partition("=")[::2]
                    checkpoints = line
            savepkt.fname = "/_libvirt/%s.cpt" % self.vmname
            savepkt.type = FT_RESTORE_FIRST
            savepkt.object_name = savepkt.fname
            DebugMessage(100, "cpt content is: '" + checkpoints + "'\n")
            savepkt.object = bytearray(json.dumps(checkpoints), encoding="utf8")
            savepkt.object_len = len(savepkt.object)
            savepkt.object_index = int(time.time())
            #shutil.rmtree(self.tempdir)
        elif self.file_to_backup == "lsn_only":
            # We have nothing to backup incremental, so we just have to pass
            # the restore object from previous job
            savepkt.fname = "/_libvirt/%s.cpt" % self.vmname
            savepkt.type = FT_RESTORE_FIRST
            savepkt.object_name = savepkt.fname
            savepkt.object = bytearray(self.row_rop_raw)
            savepkt.object_len = len(savepkt.object)
            savepkt.object_index = int(time.time())
        else:
            # should not happen
            JobMessage(
                M_FATAL,
                "Unknown error. Don't know how to handle %s\n" % self.file_to_backup,
            )

        JobMessage(
            M_INFO,
            "Starting backup of " + savepkt.fname + "\n",
        )
        return bRC_OK

    def plugin_io(self, IOP):
        """
        Called for io operations. We read from pipe into buffers or on restore
        send to xbstream
        """
        DebugMessage(200, "plugin_io called with " + str(IOP.func) + "\n")

        if IOP.func == IO_OPEN:
            DebugMessage(100, "plugin_io called with IO_OPEN\n")
            if self.log:
                try:
                    self.err_fd = open(self.log, "a")
                except IOError as msg:
                    DebugMessage(
                        100,
                        "Could not open log file (%s): %s\n"
                        % (self.log, format(str(msg))),
                    )
            if IOP.flags & (os.O_CREAT | os.O_WRONLY):
                if self.log:
                    self.err_fd.write(
                        '%s Restore Job %s opens stream with "%s"\n'
                        % (datetime.datetime.now(), self.jobId, self.restorecommand)
                    )
                self.stream = Popen(
                    self.restorecommand, shell=True, stdin=PIPE, stderr=self.err_fd
                )
            else:
                if self.log:
                    self.err_fd.write(
                        '%s Backup Job %s opens stream with "%s"\n'
                        % (datetime.datetime.now(), self.jobId, self.dumpcommand)
                    )
                self.stream = Popen(
                    self.dumpcommand, shell=True, stdout=PIPE, stderr=self.err_fd
                )
            return bRC_OK

        elif IOP.func == IO_READ:
            IOP.buf = bytearray(IOP.count)
            IOP.status = self.stream.stdout.readinto(IOP.buf)
            IOP.io_errno = 0
            return bRC_OK

        elif IOP.func == IO_WRITE:
            try:
                self.stream.stdin.write(IOP.buf)
                IOP.status = IOP.count
                IOP.io_errno = 0
            except IOError as msg:
                IOP.io_errno = -1
                DebugMessage(
                    100, "Error writing data: " + format(str(msg)) + "\n"
                )
            return bRC_OK

        elif IOP.func == IO_CLOSE:
            DebugMessage(100, "plugin_io called with IO_CLOSE\n")
            self.subprocess_returnCode = self.stream.poll()
            if self.subprocess_returnCode is None:
                # Subprocess is open, we wait until it finishes and get results
                try:
                    self.stream.communicate()
                    self.subprocess_returnCode = self.stream.poll()
                except:
                    JobMessage(
                        M_ERROR,
                        "Dump / restore command not finished properly\n",
                    )
                    bRC_Error
                return bRC_OK
            else:
                DebugMessage(
                    100,
                    "Subprocess has terminated with returncode: %d\n"
                    % self.subprocess_returnCode,
                )
                return bRC_OK

        elif IOP.func == IO_SEEK:
            return bRC_OK

        else:
            DebugMessage(
                100,
                "plugin_io called with unsupported IOP:" + str(IOP.func) + "\n",
            )
            return bRC_OK

    def end_backup_file(self):
        """
        Check if dump was successful.
        """
        # Usually the xtrabackup process should have terminated here, but on some servers
        # it has not always.
        if self.file_to_backup == "lsnfile":
            returnCode = self.subprocess_returnCode
            if returnCode != 0:
                DebugMessage(
                    100,
                    "end_backup_file() entry point in Python called. Returncode: %d\n"
                    % returnCode
                )
                return bRC_Error
        if self.file_to_backup not in ["lsnfile", "xmlfile"]:
            returnCode = self.subprocess_returnCode
            if returnCode is None:
                JobMessage(
                    M_ERROR,
                    "Dump command not finished properly for unknown reason\n",
                )
                returnCode = -99
            else:
                DebugMessage(
                    100,
                    "end_backup_file() entry point in Python called. Returncode: %d\n"
                    % self.stream.returncode,
                )
                if returnCode != 0:
                    msg = [
                        "Dump command returned non-zero value: %d" % returnCode,
                        'command: "%s"' % self.dumpcommand,
                    ]
                    if self.log:
                        msg += ['log file: "%s"' % self.log]
                    JobMessage(
                        M_FATAL, ", ".join(msg) + "\n"
                    )
            if returnCode != 0:
                return bRC_Error

            if self.log:
                self.err_fd.write(
                    "%s Backup Job %s closes stream\n"
                    % (datetime.datetime.now(), self.jobId)
                )
                self.err_fd.close()

        if self.files_to_backup:
            return bRC_More
        else:
            stopBackupCommand = 'python3 /home/banuchka/virtnbdbackup/virtnbdbackup -d %s -o - -k' % (self.vmname)
            stopBackup = Popen(stopBackupCommand, shell=True, stdout=PIPE, stderr=PIPE)
            stopBackup.wait()
            #shutil.rmtree(self.tempdir)
            return bRC_OK

    def end_restore_file(self):
        """
        Check if writing to restore command was successful.
        """
        returnCode = self.subprocess_returnCode
        if returnCode is None:
            JobMessage(
                M_ERROR,
                "Restore command not finished properly for unknown reason\n",
            )
            returnCode = -99
        else:
            DebugMessage(
                100,
                "end_restore_file() entry point in Python called. Returncode: %d\n"
                % self.stream.returncode,
            )
            if returnCode != 0:
                msg = ["Restore command returned non-zero value: %d" % return_code]
                if self.log:
                    msg += ['log file: "%s"' % self.log]
                JobMessage(M_ERROR, ", ".join(msg) + "\n")
        if self.log:
            self.err_fd.write(
                "%s Restore Job %s closes stream\n"
                % (datetime.datetime.now(), self.jobId)
            )
            self.err_fd.close()

        if returnCode == 0:
            return bRC_OK
        else:
            return bRC_Error

    def restore_object_data(self, ROP):
        """
        Called on restore and on diff/inc jobs.
        """
        # Improve: sanity / consistence check of restore object
        DebugMessage(100, "In restore:\n")
        self.row_rop_raw = ROP.object
        self.rop_data[ROP.jobid] = json.loads(str(self.row_rop_raw.decode("utf-8")))
        if len(self.rop_data[ROP.jobid]) > 0:
            self.max_to_lsn = int(len(json.loads(self.rop_data[ROP.jobid])))
            f = open('%s/%s.cpt' % (self.tempdir, self.vmname), 'w', encoding='utf-8')
            f.write(json.loads(self.row_rop_raw.decode("utf-8")))
            f.close()
            DebugMessage(100, "In restore: '" + self.tempdir + "'\n")
            JobMessage(
                M_INFO,
                "Got to checkpoint %d from restore object of job %d\n"
                % (self.max_to_lsn, ROP.jobid),
            )
        return bRC_OK


# vim: ts=4 tabstop=4 expandtab shiftwidth=4 softtabstop=4
