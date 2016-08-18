#!/usr/bin/env python

'''
reads elements from ONT fast5 file and writes them to standard output.

Copyright 2016, David Eccles (gringer) <bioinformatics@gringene.org>

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted. The software is
provided "as is" and the author disclaims all warranties with regard
to this software including all implied warranties of merchantability
and fitness. In other words, the parties responsible for running the
code are solely liable for the consequences of code execution.
'''

import os
import sys
import h5py
import numpy
from collections import deque, Counter
from itertools import islice
from bisect import insort, bisect_left
from struct import pack
from array import array

def generate_eventdir_matrix(fileName, header=True, direction=None):
    '''write out event matrix from fast5, return False if not present'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      channel = str(channelMeta["channel_number"])
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      dir = "complement" if (direction=="r") else "template"
      eventBase = "/Analyses/EventDetection_000/Reads/"
      readNames = h5File[eventBase]
      mux = 0
      # get mux for the read
      for readName in readNames:
        readMetaLocation = "/Analyses/EventDetection_000/Reads/%s" % readName
        outMeta = h5File[readMetaLocation].attrs
        mux = str(outMeta["start_mux"])
      eventLocation = "/Analyses/Basecall_1D_000/BaseCalled_%s/Events" % (dir)
      readNames = h5File[eventLocation]
      headers = h5File[eventLocation].dtype
      outData = h5File[eventLocation][()] # load entire array into memory
      if(header):
          sys.stdout.write("runID,channel,mux,read,"+",".join(headers.names)+"\n")
      # There *has* to be an easier way to do this while preserving
      # precision. Reading element by element seems very inefficient
      for line in outData:
        res=map(str,line)
        # data seems to be normalised, but just in case it isn't, here's the formula for
        # future reference: pA = (raw + offset)*range/digitisation
        # (using channelMeta[("offset", "range", "digitisation")])
        # - might also be useful to know start_time from outMeta["start_time"]
        #   which should be subtracted from event/start
        sys.stdout.write(",".join((runID,channel,mux,readName)) + "," + ",".join(res) + "\n")

def generate_event_matrix(fileName, header=True):
    '''write out event matrix from fast5, return False if not present'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      eventBase = "/Analyses/EventDetection_000/Reads/"
      readNames = h5File[eventBase]
      for readName in readNames:
        readMetaLocation = "/Analyses/EventDetection_000/Reads/%s" % readName
        eventLocation = "/Analyses/EventDetection_000/Reads/%s/Events" % readName
        outMeta = h5File[readMetaLocation].attrs
        channel = str(channelMeta["channel_number"])
        mux = str(outMeta["start_mux"])
        headers = h5File[eventLocation].dtype
        outData = h5File[eventLocation][()] # load entire array into memory
        if(header):
            sys.stdout.write("runID,channel,mux,read,"+",".join(headers.names)+"\n")
        # There *has* to be an easier way to do this while preserving
        # precision. Reading element by element seems very inefficient
        for line in outData:
          res=map(str,line)
          # data seems to be normalised, but just in case it isn't, here's the formula for
          # future reference: pA = (raw + offset)*range/digitisation
          # (using channelMeta[("offset", "range", "digitisation")])
          # - might also be useful to know start_time from outMeta["start_time"]
          #   which should be subtracted from event/start
          sys.stdout.write(",".join((runID,channel,mux,readName)) + "," + ",".join(res) + "\n")

def generate_fastq(fileName, callID="000"):
    '''write out fastq sequence(s) from fast5, return False if not present'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      eventBase = "/Analyses/EventDetection_%s/Reads/" % callID
      readNames = h5File[eventBase]
      channel = -1
      mux = -1
      readNameStr = ""
      for readName in readNames:
        readMetaLocation = "/Analyses/EventDetection_000/Reads/%s" % readName
        eventLocation = "/Analyses/EventDetection_000/Reads/%s/Events" % readName
        outMeta = h5File[readMetaLocation].attrs
        channel = str(channelMeta["channel_number"])
        mux = str(outMeta["start_mux"])
        readNameStr = str(readName)
      seqBase1D = "/Analyses/Basecall_1D_%s" % callID
      seqBase2D = "/Analyses/Basecall_2D_%s" % callID
      v1_2File = False
      if(not (seqBase1D in h5File) and (seqBase2D in h5File)):
          seqBase1D = seqBase2D
          v1_2File = True
      badEvt = 0
      if(seqBase1D in h5File):
          baseComp = "%s/BaseCalled_complement/Fastq" % seqBase1D
          baseTemp = "%s/BaseCalled_template/Fastq" % seqBase1D
          eventComp = "%s/BaseCalled_complement/Events" % seqBase1D
          eventTemp = "%s/BaseCalled_template/Events" % seqBase1D
          if(eventTemp in h5File):
              headers = h5File[eventTemp].dtype
              moveLoc = -1
              for index, item in enumerate(headers.names):
                  if(item == "move"):
                      moveLoc = index
              outEvt = h5File[eventTemp][:] # load events into memory
              mCount = Counter(map(lambda x: x[moveLoc], outEvt))
              badThresh = (sum(mCount.values()) * 0.1)
              zeroThresh = (sum(mCount.values()) * 0.9)
              # With R9, moves of 0 are more common, so ignore them unless it's *really* bad
              if(((mCount[2]) < (badThresh*2)) and (mCount[0] < zeroThresh) and
                 ((mCount[3] + mCount[4] + mCount[5] + mCount[6]) < badThresh) and (baseTemp in h5File)):
                  sys.stdout.write("@1Dtemp_"+
                                   "_".join((runID,channel,mux,readName)) + " ")
                  sys.stdout.write(str(h5File[baseTemp][()][1:]))
              else:
                  badEvt += 1
          if(eventComp in h5File):
              headers = h5File[eventComp].dtype
              moveLoc = -1
              for index, item in enumerate(headers.names):
                  if(item == "move"):
                      moveLoc = index
              outEvt = h5File[eventComp][:] # load events into memory
              mCount = Counter(map(lambda x: x[moveLoc], outEvt))
              badThresh = (sum(mCount.values()) * 0.1)
              # ignore 0 moves for R9 (unless they're *really* bad
              if(((mCount[2]) < badThresh*2) and (mCount[0] < zeroThresh) and
                 ((mCount[3] + mCount[4] + mCount[5] + mCount[6]) < badThresh) and (baseComp in h5File)):
                  sys.stdout.write("@1Dcomp_"+
                                   "_".join((runID,channel,mux,readName)) + " ")
                  sys.stdout.write(str(h5File[baseComp][()][1:]))
              else:
                  badEvt += 1
          if(badEvt == 2):
              sys.stderr.write(" [rejected: bad event data] ")
      else:
          sys.stderr.write("seqBase1D [%s] not in file\n" % seqBase1D)
      if((badEvt < 2) and seqBase2D in h5File):
          base2D = "%s/BaseCalled_2D/Fastq" % seqBase2D
          if((base2D in h5File)):
              sys.stdout.write("@2Dcons_"+
                           "_".join((runID,channel,mux,readName)) + " ")
              sys.stdout.write(str(h5File[base2D][()][1:]))

## Running median
## See [http://code.activestate.com/recipes/578480-running-median-mean-and-mode/]
def runningMedian(seq, M):
    if(M % 2 == 0):
        sys.stderr.write("Error: median window size must be odd")
        sys.exit(1)
    seq = iter(seq)
    s = []
    m = M // 2
    s = [item for item in islice(seq,M)]
    d = deque(s)
    median = lambda : s[m] # if bool(M&1) else (s[m-1]+s[m])/2
    s.sort()
    medians = [median()] * (m+1) # set initial m samples to median of first M
    for item in seq:
        old = d.popleft()          # pop oldest from left
        d.append(item)             # push newest in from right
        del s[bisect_left(s, old)] # locate insertion point and then remove old
        insort(s, item)            # insert newest such that new sort is not required
        medians.append(median())
    medians.extend([median()] * (m))
    return medians

def generate_telemetry(fileName, callID="000"):
    '''Create telemetry matrix from read files; any per-read summary
       statistics that would be useful to know'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      channel = str(channelMeta["channel_number"])
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      eventBase = "/Analyses/EventDetection_000/Reads/"
      readNames = h5File[eventBase]
      mux = 0
      # get mux for the read
      for readName in readNames:
        readMetaLocation = "/Analyses/EventDetection_000/Reads/%s" % readName
        outMeta = h5File[readMetaLocation].attrs
        mux = str(outMeta["start_mux"])
      eventLocation = "/Analyses/Basecall_1D_000/BaseCalled_%s/Events" % (dir)
      readNames = h5File[eventLocation]
      headers = h5File[eventLocation].dtype
      outData = h5File[eventLocation][()] # load entire array into memory
      if(header):
          sys.stdout.write("runID,channel,mux,read,"+",".join(headers.names)+"\n")
      # There *has* to be an easier way to do this while preserving
      # precision. Reading element by element seems very inefficient
      for line in outData:
        res=map(str,line)
        # data seems to be normalised, but just in case it isn't, here's the formula for
        # future reference: pA = (raw + offset)*range/digitisation
        # (using channelMeta[("offset", "range", "digitisation")])
        # - might also be useful to know start_time from outMeta["start_time"]
        #   which should be subtracted from event/start
        sys.stdout.write(",".join((runID,channel,mux,readName)) + "," + ",".join(res) + "\n")

def generate_raw(fileName, callID="000", medianWindow=21):
    '''write out raw sequence from fast5, with optional running median
       smoothing, return False if not present'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      eventBase = "/Raw/Reads"
      if(not eventBase in h5File):
          return False
      readNames = h5File[eventBase]
      readNameStr = ""
      for readName in readNames:
        readRawLocation = "%s/%s/Signal" % (eventBase, readName)
        outData = h5File[readRawLocation][()] # load entire raw data into memory
        if(medianWindow==1):
            sys.stdout.write(outData)
        else:
            array("H",runningMedian(outData, M=medianWindow)).tofile(sys.stdout)

def generate_dir_raw(fileName, callID="000", medianWindow=1, direction=None):
    '''write out directional raw sequence from fast5, return False if not present'''
    try:
        h5File = h5py.File(fileName, 'r')
        h5File.close()
    except:
        return False
    with h5py.File(fileName, 'r') as h5File:
      runMeta = h5File['UniqueGlobalKey/tracking_id'].attrs
      channelMeta = h5File['UniqueGlobalKey/channel_id'].attrs
      runID = '%s_%s' % (runMeta["device_id"],runMeta["run_id"][0:16])
      eventBase = "/Raw/Reads"
      if(not eventBase in h5File):
          return False
      seqBase1D = "/Analyses/Basecall_1D_%s" % callID
      dir = "complement" if (direction=="r") else "template"
      eventMetaBase = "%s/BaseCalled_%s/Events" % (seqBase1D, dir)
      if(not eventMetaBase in h5File):
          return False
      eventMeta = h5File[eventMetaBase].attrs
      absRawStart = eventMeta["start_time"] * channelMeta["sampling_rate"]
      absRawEnd = (eventMeta["start_time"]
                + eventMeta["duration"]) * channelMeta["sampling_rate"]
      readNames = h5File[eventBase]
      readNameStr = ""
      for readName in readNames:
        readRawMeta = h5File["%s/%s" % (eventBase, readName)].attrs
        relRawStart = int(absRawStart - readRawMeta["start_time"])
        relRawEnd = int(absRawEnd - readRawMeta["start_time"])
        sys.stderr.write("Writing (%d..%d) from %s\n" %
                         (relRawStart, relRawEnd, readName))
        readRawLocation = "%s/%s/Signal" % (eventBase, readName)
        signal = h5File[readRawLocation][relRawStart:relRawEnd] # subset for direction
        ## Remove extreme values from signal
        meanSig = sum(signal) / len(signal)
        madSig = sum(map(lambda x: abs(x - meanSig), signal)) / len(signal)
        minSig = meanSig - madSig * 6
        maxSig = meanSig + madSig * 6
        rangeFilt = numpy.vectorize(lambda x: meanSig if
                                    ((x < minSig) or (x > maxSig)) else x);
        signal = rangeFilt(signal)
        sys.stdout.write(signal) # write to file

def usageQuit():
    sys.stderr.write('Error: No file or directory provided in arguments\n\n')
    sys.stderr.write('Usage: %s <dataType> <fast5 file name>\n' % sys.argv[0])
    sys.stderr.write(' where <dataType> is one of the following:\n')
    sys.stderr.write('  fastq     - extract base-called fastq data\n')
    sys.stderr.write('  event     - extract uncalled model event matrix\n')
    sys.stderr.write('  eventfwd  - extract model event matrix (template)\n')
    sys.stderr.write('  eventrev  - extract model event matrix (complement)\n')
    sys.stderr.write('  telemetry - extract read statistics matrix\n')
    sys.stderr.write('  raw       - extract raw data without smoothing\n')
    sys.stderr.write('  rawfwd    - extract raw data from template\n')
    sys.stderr.write('  rawrev    - extract raw data from complement\n')
    sys.stderr.write('  rawsmooth - raw data, running-median smoothing\n')
    sys.exit(1)

if len(sys.argv) < 3:
    usageQuit()

dataType = sys.argv[1]
if(not dataType in ("fastq", "fasta", "event", "eventfwd",
                    "eventrev", "telemetry", "raw", "rawfwd", "rawrev", "rawsmooth")):
    sys.stderr.write('Error: Incorrect dataType\n\n')
    usageQuit()

fileArg = sys.argv[2]
seenHeader = False

if(os.path.isdir(fileArg)):
    sys.stderr.write("Processing directory '%s':\n" % fileArg)
    for dirPath, dirNames, fileNames in os.walk(fileArg):
        fc = len(fileNames)
        for fileName in fileNames:
            if(fileName.endswith(".fast5")): # only process fast5 files
                sys.stderr.write("  Processing file '%s'..." % fileName)
                if(dataType == "event"):
                    generate_event_matrix(os.path.join(dirPath, fileName), not seenHeader)
                elif(dataType == "telemetry"):
                    generate_telemetry_matrix(os.path.join(dirPath, fileName), not seenHeader)
                elif(dataType == "fastq"):
                    generate_fastq(os.path.join(dirPath, fileName))
                elif(dataType == "raw"):
                    sys.stderr.write(" Error: raw output only works for single files!\n")
                    usageQuit()
                fc -= 1
                seenHeader = True
                if(fc == 1):
                    sys.stderr.write(" done (%d more file to process)\n" % fc)
                else:
                    sys.stderr.write(" done (%d more files to process)\n" % fc)
elif(os.path.isfile(fileArg)):
    if(dataType == "event"):
        generate_event_matrix(fileArg)
    elif(dataType == "eventfwd"):
        generate_eventdir_matrix(fileArg, direction="f")
    elif(dataType == "eventrev"):
        generate_eventdir_matrix(fileArg, direction="r")
    elif(dataType == "telemetry"):
        generate_telemetry_matrix(fileArg)
    elif(dataType == "fastq"):
        generate_fastq(fileArg)
    elif(dataType == "rawsmooth"):
        generate_raw(fileArg, medianWindow=21)
    elif(dataType == "raw"):
        generate_raw(fileArg)
    elif(dataType == "rawfwd"):
        generate_dir_raw(fileArg, direction="f")
    elif(dataType == "rawrev"):
        generate_dir_raw(fileArg, direction="r")
else:
    usageQuit()
