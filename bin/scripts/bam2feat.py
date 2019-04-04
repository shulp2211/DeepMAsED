#!/usr/bin/env python
from __future__ import print_function
import sys,os
import argparse
import logging
import itertools
from functools import partial
from multiprocessing import Pool

import pysam


desc = 'Creating DL features from bam/sam file'
epi = """DESCRIPTION:
The bam file should be indexed via `samtools index`.
The fasta file should be indexed via `samtools faidx`.

The output table is written to STDOUT.
"""
parser = argparse.ArgumentParser(description=desc,
                                 epilog=epi,
                                 formatter_class=argparse.RawTextHelpFormatter)
parser.add_argument('bam_file', metavar='bam_file', type=str,
                    help='bam (or sam) file')
parser.add_argument('fasta_file', metavar='fasta_file', type=str,
                    help='Reference sequences for the bam (sam) file')
parser.add_argument('-a', '--assembler', type=str, default='unknown',
                    help='Name of metagenome assembler used to create the contigs (default: %(default)s)')
parser.add_argument('-p', '--procs', type=int, default=1,
                    help='Number of parallel processes (default: %(default)s)')
parser.add_argument('--version', action='version', version='0.0.1')


logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.DEBUG)


IDX = {'A':0, 'C':1, 'G':2, 'T':3}

def count_SNPs(query_seqs, ref_seq):
    SNP_cnt = 0
    for i,x in enumerate(query_seqs):
        if i != IDX[ref_seq]:
            SNP_cnt += x[0]
    return SNP_cnt

def _contig_stats(contig, bam_file, fasta_file, assembler):

    fasta = pysam.FastaFile(fasta_file)
    
    x = 'rb' if bam_file.endswith('.bam') else 'r'
    
    with pysam.AlignmentFile(bam_file, x) as inF:
        stats = []
        contig_i = inF.references.index(contig)
        for pos in range(0,inF.lengths[contig_i]):
            # ref seq
            ref_seq = fasta.fetch(contig, pos, pos+1)
            # query seq
            query_seq = inF.count_coverage(contig, pos, pos+1)
            # SNPs
            SNPs = count_SNPs(query_seq, ref_seq)
            # coverage
            coverage = sum([x[0] for x in query_seq])
            # reads
            n_discord = 0
            n_sup = 0
            n_sec = 0
            for read in inF.fetch(contig, pos, pos+1):
                ## discordant reads
                if (read.is_paired == True and
                    read.is_proper_pair == False and
                    read.is_unmapped == False and
                    read.mate_is_unmapped == False):
                    n_discord += 1
                ## sup/sec reads
                if read.is_supplementary:
                    n_sup += 1
                if read.is_secondary:
                    n_sec += 1
            
            # columns
            stats.append([
                assembler,
                contig,
                str(pos),
                ref_seq,
                str(query_seq[0][0]),
                str(query_seq[1][0]),
                str(query_seq[2][0]),
                str(query_seq[3][0]),
                str(SNPs),
                str(coverage),
                str(n_discord),
                str(n_sup),
                str(n_sec)
            ])
        return stats

def contig_stats(contigs, bam_file, fasta_file, assembler):
    stats = []
    for contig in contigs:
        x = _contig_stats(contig, bam_file, fasta_file, assembler)
        stats.append(x)
    return stats

def batch_contigs(contigs, nprocs):
    msg = 'Batching contigs into {} equal bins'
    logging.info(msg.format(nprocs))
    
    contig_bins = {}
    for contig,_bin in zip(contigs, itertools.cycle(range(0,nprocs))):
        try:
            contig_bins[_bin].append(contig)
        except KeyError:
            contig_bins[_bin] = [contig]
    return contig_bins.values()

def main(args):
    # header
    H = ['assembler', 'contig', 'position', 'ref_base',
         'num_query_A', 'num_query_C', 'num_query_G', 'num_query_T',
         'num_SNPs', 'coverage', 'num_discordant',
         'num_supplementary', 'num_secondary']
    print('\t'.join(H))
    
    # Getting contig list
    x = 'rb' if args.bam_file.endswith('.bam') else 'r'
    contigs = []
    with pysam.AlignmentFile(args.bam_file, x) as inF:
        contigs = inF.references
        contigs = contigs[:30]
    msg = 'Number of contigs in the bam file: {}'
    logging.info(msg.format(len(contigs)))
        
    # getting contig stats
    func = partial(contig_stats, bam_file=args.bam_file,
                   fasta_file=args.fasta_file, assembler=args.assembler)
    if args.procs > 1:
        p = Pool(args.procs)
        # batching contigs for multiprocessing
        contig_bins = batch_contigs(contigs, args.procs)
        # getting stats
        stats = p.map(func, contig_bins)
    else:
        # getting status
        stats = map(func, [contigs])
        
    # printing results
    logging.info('Writing feature table to STDOUT')
    for x in stats:
        for y in x:
            for z in y:
                print('\t'.join(z))

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
