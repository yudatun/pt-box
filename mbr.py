#!/usr/bin/env python
#
# Copyright (C) 2015 The Yudatun Open Source Project
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#

import os
import sys
import struct

import pt

INSTRUCTIONS = pt.INSTRUCTIONS
PARTITIONS   = pt.PARTITIONS
BUG          = pt.BUG

BYTES_PER_SECTOR = pt.BYTES_PER_SECTOR

class Entry(object):

  def __init__(self):
    self.bootable              = 0x00
    self.first_sector_head     = 0x00
    self.first_sector_sec_cy   = 0x00 # 5~0 sector; 7~6 cylinder high bits
    self.first_sector_cylinder = 0x00 # cylinder low bits
    self.part_type             = 0x00
    self.last_sector_head      = 0x00
    self.last_sector_sec_cy    = 0x00
    self.last_sector_cylinder  = 0x00
    self.first_lba             = 0x00000000
    self.num_sectors           = 0x00000000

    self.array = [0] * 16

  def toarray(self):

    self.array[0] = self.bootable;
    self.array[1] = self.first_sector_head;
    self.array[2] = self.first_sector_sec_cy;
    self.array[3] = self.first_sector_cylinder;
    self.array[4] = self.part_type;
    self.array[5] = self.last_sector_head;
    self.array[6] = self.last_sector_sec_cy;
    self.array[7] = self.last_sector_cylinder;

    i = 8
    for b in range(4):
      self.array[i] = (self.first_lba >> (b * 8)) & 0xFF
      i += 1

    i = 12
    for b in range(4):
      self.array[i] = (self.num_sectors >> (b * 8)) & 0xFF
      i += 1

class MBR(object):

  def __init__(self):
    self.code_start        = 0x0
    self.signature_start   = 0x1B8  # 440
    self.reserve_start     = 0x1BC  # 444
    self.entry_array_start = 0x1BE  # 446
    self.magic_0_start     = 0x1FE  # 510
    self.magic_1_start     = 0x1FF  # 511

    self.code        = None
    self.signature   = 0x00000000
    self.reserve     = 0x0000
    self.entry_array = []
    self.magic_0     = 0x55
    self.magic_1     = 0xAA

    self.array = [0] * 512

  def binfile2code(self, filename):
    if filename is None:
      return None

    file_size = os.path.getsize(filename)
    if file_size != 440 and file_size != 446:
      BUG.error("Invalid boot code file (%s) for MBR" % filename)

    self.code = [0] * file_size
    with open(filename, 'rb') as f:
      data = f.read(file_size)
      i = 0
      for b in data:
        self.code[i] = ord(b); i += 1
      f.close()

  def add_entry(self, entry):
    self.entry_array.append(entry)

  def toarray(self):
    i = 0

    if self.code is not None:
      i = self.code_start
      for b in self.code:
        self.array[i] = b
        i += 1

    if self.signature is not None:
      i = self.signature_start
      self.array[i]   = (self.signature >> 24) & 0xFF
      self.array[i+1] = (self.signature >> 16) & 0xFF
      self.array[i+2] = (self.signature >> 8)  & 0xFF
      self.array[i+3] = (self.signature)       & 0xFF

    if self.reserve is not None:
      i = self.reserve_start
      self.array[i]   = (self.reserve >> 8) & 0xFF
      self.array[i+1] = (self.reserve)      & 0xFF

    if len(self.entry_array) > 0:
      i = self.entry_array_start
      for entry in self.entry_array:
        for b in entry.array:
          self.array[i] = b
          i += 1

    self.array[self.magic_0_start] = self.magic_0
    self.array[self.magic_1_start] = self.magic_1

  def init_partition_table(self, part_num):

    kb_per_bulk = INSTRUCTIONS.WRITE_PROTECT_BULK_SIZE_IN_KB
    sectors_per_bulk = pt.kb2sectors(kb_per_bulk)

    first_lba = 1
    last_lba  = 1

    for i in range(part_num):

      part = PARTITIONS.part_list[i]
      last_wp_chunk = PARTITIONS.wp_chunk_list[-1]

      if part.first_lba_in_kb > 0:
        first_lba = pt.kb2sectors(part.first_lba_in_kb)
      if first_lba < last_lba:
        first_lba = last_lba

      part.readonly = True
      PARTITIONS.update_wp_chunk_list(first_lba, part.size_in_sec, sectors_per_bulk)

      entry = Entry()
      if part.bootable is True:
        entry.bootable = 0x80
      else:
        entry.bootable = 0x00
      entry.part_type   = part._type
      entry.first_lba   = first_lba
      entry.num_sectors = part.size_in_sec
      entry.toarray()

      self.add_entry(entry)

      last_lba = first_lba + part.size_in_sec

  def create(self, output_directory, boot_file, part_num):

    image_file = "%sMBR.bin" % output_directory

    self.binfile2code(boot_file)
    self.signature = INSTRUCTIONS.DISK_SIGNATURE
    self.init_partition_table(part_num)
    self.toarray()

    BUG.green("Create %s <-- Master Boot Recorder" % image_file)
    with open(image_file, 'wb') as f:
      for b in self.array:
        f.write(struct.pack('B', b))

class MBRPartitionTable(object):

  def __init__(self):
    self.mbr = MBR()
    self.ebr = None

  def create(self, output_directory, boot_file):
    part_num = len(PARTITIONS.part_list)
    if part_num <= 4:
      print "We can get away with only an MBR"
      self.mbr.create(output_directory, boot_file, part_num)
    else:
      print "We will need an MBR and %d EBRS" % (self.part_num - 3)
