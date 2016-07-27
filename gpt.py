#!/usr/bin/env python
#
# Copyright (C) 2015 The Yudatun Open Source Project
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation
#

import random
import struct

import pt
import common
import mbr

OPTIONS = common.OPTIONS

INSTRUCTIONS = pt.INSTRUCTIONS
PARTITIONS   = pt.PARTITIONS
BUG          = pt.BUG

BYTES_PER_SECTOR = pt.BYTES_PER_SECTOR

# A8h reflected is 15h, i.e. 10101000 <--> 00010101
def reflect(data, bits):
  reflection = 0x00000000
  for bit in range(bits):
    if (data & 0x01):
      reflection |= (1 << ((bits - 1) - bit))

    data = (data >> 1);

  return reflection

def my_crc32(array, num):
  k         = 8            # length of unit (i.e. byte)
  MSB       = 0
  gx        = 0x04C11DB7   # IEEE 32bit polynomial
  regs      = 0xFFFFFFFF   # init to all ones
  regs_mask = 0xFFFFFFFF   # ensure only 32 bit answer

  for i in range(num):
    data = array[i]
    data = reflect(data, 8)
    for j in range(k):
      MSB  = data >> (k - 1)  # get MSB
      MSB &= 1                # ensure just 1 bit
      regs_MSB = (regs >> 31) & 1
      regs = regs << 1        # shift regs for CRC-CCITT
      if regs_MSB ^ MSB:      # MSB is a 1
        regs = regs ^ gx      # XOR with generator poly
      regs = regs & regs_mask # Mask off excess upper bits
      data <<= 1              # get to next bit

  regs  = regs & regs_mask # Mask off excess upper bits
  crc32 = reflect(regs, 32) ^ 0xFFFFFFFF

  return crc32

class GPTHeader(object):

  def __init__(self, is_primary):

    # [0x45, 0x46, 0x49, 0x20, 0x50, 0x41, 0x52, 0x54] - 'EFI PART'
    self.signature             = 0x5452415020494645
    self.revision              = 0x00010000  # [0x00, 0x00, 0x01, 0x00]
    self.header_size           = 0x0000005C  # [0x5C, 0x00, 0x00, 0x00] - 92
    self.header_crc32          = 0x00000000  # *
    self.reserve               = 0x00000000
    if is_primary is True:
      self.current_lba           = 1
      self.backup_lba            = 0
    else:
      self.current_lba           = 0
      self.backup_lba            = 1
    self.first_lba             = 0x0000000000000022  # 34
    self.last_lba              = 0x0000000000000000  # 0 *
    self.disk_guid             = 0x200C003DB32B6EA04BF2BBE298101B32  # *
    if is_primary is True:
      self.entry_array_start_lba = 0x0000000000000002
    else:
      self.entry_array_start_lba = 0x0000000000000000
    self.entry_number          = 0x00000000  # *
    self.entry_size            = 0x00000080  # 128
    self.entry_array_crc32     = 0x00000000  # *

    self.array = [0] * BYTES_PER_SECTOR

  def toarray(self):
    i = 0
    for b in range(8):
      self.array[i] = (self.signature >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.revision >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.header_size >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.header_crc32 >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.reserve >> (b * 8)) & 0xFF
      i += 1
    for b in range(8):
      self.array[i] = (self.current_lba >> (b * 8)) & 0xFF
      i += 1
    for b in range(8):
      self.array[i] = (self.backup_lba >> (b * 8)) & 0xFF
      i += 1
    for b in range(8):
      self.array[i] = (self.first_lba >> (b * 8)) & 0xFF
      i += 1
    for b in range(8):
      self.array[i] = (self.last_lba >> (b * 8)) & 0xFF
      i += 1
    for b in range(16):
      self.array[i] = (self.disk_guid >> (b * 8)) & 0xFF
      i += 1
    for b in range(8):
      self.array[i] = (self.entry_array_start_lba >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.entry_number >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.entry_size >> (b * 8)) & 0xFF
      i += 1
    for b in range(4):
      self.array[i] = (self.entry_array_crc32 >> (b * 8)) & 0xFF
      i += 1

  def update(self, last_lba, entry_number, entry_array_crc32):
    if last_lba is not None and last_lba > 0:
      self.last_lba = last_lba
    if entry_number is not None and entry_number > 0:
      self.entry_number = entry_number
    if entry_array_crc32 is not None:
      self.entry_array_crc32 = entry_array_crc32
    self.toarray()
    self.header_crc32 = my_crc32(self.array, self.header_size)

class Entry(object):

  def __init__(self):
    self.type_guid   = None
    self.unique_guid = None
    self.first_lba   = None
    self.last_lba    = None
    self.attributes  = None
    self.label       = None

    self.array = [0] * (BYTES_PER_SECTOR / 4)

  def set(self, type_guid, unique_guid, first_lba, last_lba, attributes, label):
    self.type_guid   = type_guid
    self.unique_guid = unique_guid
    self.first_lba   = first_lba
    self.last_lba    = last_lba
    self.attributes  = attributes
    if len(label) > 36:
        self.label = label[0:36]
    else:
      self.label = label

  def toarray(self):
    i = 0

    if self.type_guid is not None:
      for b in range(16):
        self.array[i] = (self.type_guid >> (b * 8)) & 0xFF
        i += 1

    if self.unique_guid is not None:
      for b in range(16):
        self.array[i] = (self.unique_guid >> (b * 8)) & 0xFF
        i += 1

    if self.first_lba is not None:
      for b in range(8):
        self.array[i] = (self.first_lba >> (b * 8)) & 0xFF
        i += 1

    if self.last_lba is not None:
      for b in range(8):
        self.array[i] = (self.last_lba >> (b * 8)) & 0xFF
        i += 1

    if self.attributes is not None:
      for b in range(8):
        self.array[i] = (self.attributes >> (b * 8)) & 0xFF
        i += 1

    if self.label is not None:
      if len(self.label) > 36:
        self.label = self.label[0:36]
      for b in self.label:
        self.array[i] = ord(b); i += 1
        self.array[i] = 0x00;   i += 1

class PrimaryGPT(object):

  def __init__(self):
    self.gpt_header  = GPTHeader(True)
    self.entry_array = []

    self.first_partition_lba = 34

    self.array = [0x00] * (33 * BYTES_PER_SECTOR)

    self.gpt_header_addr  = 0
    self.entry_array_addr = 1 * BYTES_PER_SECTOR

  def add_entry(self, entry):
    self.entry_array.append(entry)

  def toarray(self):

    if self.gpt_header is not None:
      i = self.gpt_header_addr
      for b in self.gpt_header.array:
        self.array[i] = b
        i += 1

    if len(self.entry_array) > 0:
      i = self.entry_array_addr
      for entry in self.entry_array:
        for b in entry.array:
          self.array[i] = b
          i += 1

  def entry_array_crc32(self, entry_number):

    if entry_number <= 0 or entry_number > 128:
      BUG.error("Invalidate number of entries (%d)." % entry_number)

    entry_size = self.gpt_header.entry_size
    array = [0] * entry_number * entry_size
    if len(self.entry_array) > 0:
      i = 0
      for entry in self.entry_array:
        for b in entry.array:
          array[i] = b
          i += 1

    return my_crc32(array, entry_number * entry_size)

  def update_gpt_header(self, last_lba, entry_number, entry_array_crc32):
    self.gpt_header.update(last_lba, entry_number, entry_array_crc32)
    self.gpt_header.toarray()

class SecondaryGPT(object):

  def __init__(self):
    self.entry_array = []
    self.gpt_header  = GPTHeader(False)

    self.array = [0x00] * (33 * BYTES_PER_SECTOR)

    self.entry_array_addr = 0
    self.gpt_header_addr  = 32 * BYTES_PER_SECTOR

  def update_gpt_header(self, last_lba, entry_number, entry_array_crc32):
    self.gpt_header.update(last_lba, entry_number, entry_array_crc32)
    self.gpt_header.toarray()

  def toarray(self):

    if len(self.entry_array) > 0:
      i = self.entry_array_addr
      for entry in self.entry_array:
        for b in entry.array:
          self.array[i] = b
          i += 1

    if self.gpt_header is not None:
      i = self.gpt_header_addr
      for b in self.gpt_header.array:
        self.array[i] = b
        i += 1

class GPTPartitionTable(object):

  def __init__(self):
    self.protective_mbr = mbr.MBR()
    self.primary_gpt    = PrimaryGPT()
    self.secondary_gpt  = SecondaryGPT()

  def init_protective_mbr(self):
    entry = mbr.Entry()
    entry.bootable              = 0x00
    entry.first_sector_head     = 0x00
    entry.first_sector_sec_cy   = 0x01
    entry.first_sector_cylinder = 0x00
    entry.part_type             = 0xEE
    entry.last_sector_head      = 0xFF
    entry.last_sector_sec_cy    = 0xFF
    entry.last_sector_cylinder  = 0xFF
    entry.first_lba             = 0x00000001
    entry.num_sectors           = 0xFFFFFFFF
    entry.toarray()

    self.protective_mbr.signature = INSTRUCTIONS.DISK_SIGNATURE
    self.protective_mbr.add_entry(entry)
    self.protective_mbr.toarray()

  def init_primary_gpt(self):
    first_lba = self.primary_gpt.first_partition_lba
    last_lba  = first_lba
    sectors_till_next_bulk = 0

    kb_per_bulk = INSTRUCTIONS.WRITE_PROTECT_BULK_SIZE_IN_KB
    sectors_per_bulk = pt.kb2sectors(kb_per_bulk)

    print '='*60
    print '| PartName    Size(KB)  Readonly FirstLBA  LastLBA'
    print '='*60

    for i in range(len(PARTITIONS.part_list)):

      part = PARTITIONS.part_list[i]
      last_wp_chunk = PARTITIONS.wp_chunk_list[-1]

      if kb_per_bulk > 0:
        sectors_till_next_bulk = pt.sectors_till_next_bulk(first_lba, kb_per_bulk)

      if part.readonly is True:
        # To be here means this partition is read-only, so see if
        # we need to move the start lba
        if first_lba > last_wp_chunk.end_sector:
          first_lba += sectors_till_next_bulk
        PARTITIONS.update_wp_chunk_list(first_lba, part.size_in_sec, sectors_per_bulk)
      else:
        # To be here means this partition is writeable, so see if
        # we need to move the start
        if first_lba <= last_wp_chunk.end_sector:
          first_lba += sectors_till_next_bulk

      # The last partition
      if (i + 1) == len(PARTITIONS.part_list) and \
         INSTRUCTIONS.AUTO_GROW_LAST_PARTITION is True:
        part.size_in_kb = part.size_in_sec = 0 # Infinite huge

      # Increase by number of sectors, last lba inclusive, so add 1 for size.
      last_lba = first_lba + part.size_in_sec
      # Inclusive, meaning 0 to 3 is 4 sectors, or another way,
      # last lba must be odd.
      last_lba -= 1

      unique_guid = 0x0
      if OPTIONS.sequential_guid is True:
        unique_guid = i + 1
      elif part.uniqueguid != "":
        unique_guid = part.uniqueguid
      else:
        unique_guid = random.randint(0, 2 ** (128))

      attributes = 0x0
      if part.readonly is True:
        attributes |= 1 << 60
      if part.hidden is True:
        attributes |= 1 << 62
      if part.dontautomount is True:
        attributes |= 1 << 63
      if part.system is True:
        attributes |= 1

      entry = Entry()
      entry.set(part._type, unique_guid, first_lba, \
                last_lba, attributes, part.label)
      entry.toarray()
      self.primary_gpt.add_entry(entry)

      print "| %-12s%-10d%-9s%-10d%-d" \
        % (part.label, part.size_in_kb, str(part.readonly), first_lba, last_lba)
      print '-'*60

      first_lba = last_lba + 1
      last_lba  = first_lba

    if INSTRUCTIONS.AUTO_GROW_LAST_PARTITION is False:
      last_lba += 32 # 33 - 1 (Size of Secondary GPT - 1)
    else:
      last_lba = 0x0

    # Calculate to the numbers of entry items into array.
    real_entry_number = len(PARTITIONS.part_list)
    entry_number = 0
    if OPTIONS.all_128_partitions is True:
      entry_number = 128
    else:
      entry_number = (real_entry_number / 4) * 4
      if real_entry_number % 4 > 0:
        entry_number += 4
    entry_array_crc32 = self.primary_gpt.entry_array_crc32(entry_number)

    self.primary_gpt.update_gpt_header(last_lba, entry_number, \
                                       entry_array_crc32)
    self.primary_gpt.toarray()

  def init_secondary_gpt(self):
    self.secondary_gpt.entry_array = self.primary_gpt.entry_array[:]
    last_lba = self.primary_gpt.gpt_header.last_lba
    entry_number = self.primary_gpt.gpt_header.entry_number
    entry_array_crc32 = self.primary_gpt.gpt_header.entry_array_crc32
    self.secondary_gpt.update_gpt_header(last_lba, entry_number, \
                                         entry_array_crc32)
    self.secondary_gpt.toarray()

  def create_gpt_both_bin(self, output_directory):
    image_file = "%sgpt_both.bin" % output_directory

    BUG.green("Create %s <-- Protective MBR + Primary GPT + Backup GPT." % image_file)
    with open(image_file, "wb") as f:
      for b in self.protective_mbr.array:
        f.write(struct.pack("B", b))
      for b in self.primary_gpt.array:
        f.write(struct.pack("B", b))
      for b in self.secondary_gpt.array:
        f.write(struct.pack("B", b))

  def create_gpt_main_bin(self, output_directory):
    image_file = "%sgpt_main.bin" % output_directory

    BUG.green("Create %s <-- Protective MBR + Primary GPT." % image_file)
    with open(image_file, "wb") as f:
      for b in self.protective_mbr.array:
        f.write(struct.pack("B", b))
      for b in self.primary_gpt.array:
        f.write(struct.pack("B", b))

  def create_gpt_backup_bin(self, output_directory):
    image_file = "%sgpt_backup.bin" % output_directory

    BUG.green("Create %s <-- Backup GPT." % image_file)
    with open(image_file, "wb") as f:
      for b in self.secondary_gpt.array:
        f.write(struct.pack("B", b))

  def create(self, output_directory):
    self.init_protective_mbr()
    self.init_primary_gpt()
    self.init_secondary_gpt()

    print "| Protective MBR CRC32: 0x%X" \
      % my_crc32(self.protective_mbr.array, BYTES_PER_SECTOR)
    print '-'*60
    print "| Primary GPT Header CRC32: 0x%X" \
      % self.primary_gpt.gpt_header.header_crc32
    print '-'*60
    print "| Primary Entry Array CRC32: 0x%X" \
      % self.primary_gpt.gpt_header.entry_array_crc32
    print '-'*60
    print "| Secondary GPT Header CRC32: 0x%X" \
      % self.secondary_gpt.gpt_header.header_crc32
    print '-'*60
    print "| Secondary Entry Array CRC32: 0x%X" \
      % self.secondary_gpt.gpt_header.entry_array_crc32
    print '-'*60

    self.create_gpt_both_bin(output_directory)
    self.create_gpt_main_bin(output_directory)
    self.create_gpt_backup_bin(output_directory)
