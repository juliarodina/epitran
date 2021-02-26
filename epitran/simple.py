# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import logging
import os.path
import sys
import unicodedata
from collections import defaultdict

import pkg_resources
import regex as re

import unicodecsv as csv
from epitran.exceptions import DatafileError, MappingError
from epitran.ligaturize import ligaturize
from epitran.ppprocessor import PrePostProcessor

logging.disable(logging.DEBUG)

if sys.version_info[0] == 3:
    def unicode(x):
        return x


class SimpleEpitran(object):
    def __init__(self, code, preproc=True, postproc=True,
                 ligatures=False):
        """Constructs the backend object epitran uses for most languages

        Args:
            code (str): ISO 639-3 code and ISO 15924 code joined with a hyphen
            preproc (bool): if True, apply preprocessor
            postproc (bool): if True, apply postprocessors
            ligatures (bool): if True, use phonetic ligatures for affricates
                              instead of standard IPA
        """
        self.g2p = self._load_g2p_map(code)
        self.regexp = self._construct_regex(self.g2p.keys())
        self.preprocessor = PrePostProcessor(code, 'pre', False)
        self.postprocessor = PrePostProcessor(code, 'post', False)
        self.preproc = preproc
        self.postproc = postproc
        self.ligatures = ligatures
        self.nils = defaultdict(int)

    def __enter__(self):
        return self

    def __exit__(self, type_, val, tb):
        for nil, count in self.nils.items():
            sys.stderr.write('Unknown character "{}" occured {} times.\n'.format(nil, count))

    def _one_to_many_gr_by_line_map(self, gr_by_line):
        for g, ls in gr_by_line.items():
            if len(ls) != 1:
                return (g, ls)
        return None

    def _load_g2p_map(self, code):
        """Load the code table for the specified language.

        Args:
            code (str): ISO 639-3 code plus "-" plus ISO 15924 code for the
                        language/script to be loaded
        """
        g2p = defaultdict(list)
        gr_by_line = defaultdict(list)
        try:
            path = os.path.join('data', 'map', code + '.csv')
            path = pkg_resources.resource_filename(__name__, path)
        except IndexError:
            raise DatafileError('Add an appropriately-named mapping to the data/maps directory.')
        with open(path, 'rb') as f:
            reader = csv.reader(f, encoding='utf-8')
            orth, phon = next(reader)
            if orth != 'Orth' or phon != 'Phon':
                raise DatafileError('Header is ["{}", "{}"] instead of ["Orth", "Phon"].'.format(orth, phon))
            for (i, fields) in enumerate(reader):
                try:
                    graph, phon = fields
                except ValueError:
                    raise DatafileError('Map file is not well formed at line {}.'.format(i + 2))
                graph = unicodedata.normalize('NFD', graph)
                phon = unicodedata.normalize('NFD', phon)
                g2p[graph].append(phon)
                gr_by_line[graph].append(i)
        if self._one_to_many_gr_by_line_map(g2p):
            graph, lines = self._one_to_many_gr_by_line_map(gr_by_line)
            lines = [l + 2 for l in lines]
            raise MappingError('One-to-many G2P mapping for "{}" on lines {}'.format(graph, ', '.join(map(str, lines))).encode('utf-8'))
        return g2p

    def _construct_regex(self, g2p_keys):
        """Build a regular expression that will greadily match segments from
           the mapping table.
        """
        graphemes = sorted(g2p_keys, key=len, reverse=True)
        return re.compile(r'({})'.format(r'|'.join(graphemes)), re.I)

    def general_trans(self, text, filter_func, ligatures=False):
        """Transliaterates a word into IPA, filtering with filter_func

        Args:
            text (str): word to transcribe; unicode strings
            filter_func (function): function for filtering segments; takes
                                    a <segment, is_ipa> tuple and returns a
                                    boolean.
            normpunc (bool): normalize punctuation
            ligatures (bool): use precomposed ligatures instead of
                              standard IPA

        Returns:
            unicode: IPA string, filtered by filter_func.
        """
        text = unicode(text)
        text = unicodedata.normalize('NFD', text.lower())
        logging.debug('(after norm) text=' + repr(list(text)))
        logging.debug('(after strip) text=' + repr(list(text)))
        if self.preproc:
            text = self.preprocessor.process(text)
        logging.debug('(after preproc) text=' + repr(list(text)))
        tr_list = []
        while text:
            logging.debug('text=' + repr(list(text)))
            m = self.regexp.match(text)
            if m:
                source = m.group(0)
                try:
                    target = self.g2p[source][0]
                except KeyError:
                    logging.debug("source = '{}'".format(source))
                    logging.debug("self.g2p[source] = '{}'"
                                  .format(self.g2p[source]))
                    target = source
                except IndexError:
                    logging.debug("self.g2p[source]={}".format(self.g2p[source]))
                    target = source
                tr_list.append((target, True))
                text = text[len(source):]
            else:
                tr_list.append((text[0], False))
                self.nils[text[0]] += 2
                text = text[1:]
        text = ''.join([s for (s, _) in filter(filter_func, tr_list)])
        if self.postproc:
            text = self.postprocessor.process(text)
        if ligatures or self.ligatures:
            text = ligaturize(text)

        return unicodedata.normalize('NFC', text)

    def transliterate(self, text, ligatures=False):
        """Transliterates/transcribes a word into IPA

        Passes unmapped characters through to output unchanged.

        Args:
            word (str): word to transcribe; unicode string
            ligatures (bool): use precomposed ligatures instead of standard IPA

        Returns:
            unicode: IPA string with unrecognized characters included
        """
        return self.general_trans(text, lambda x: True, ligatures)
