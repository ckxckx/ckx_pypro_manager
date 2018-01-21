"""
Copyright (c) 2017 Dependable Systems Laboratory, EPFL

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


import logging
import os
import sys

from s2e_env.command import ProjectCommand, CommandError
from . import get_tb_files, parse_tb_file
from . import line_info

logger = logging.getLogger('lcov')


class LineCoverage(ProjectCommand):
    """
    Generate a line coverage report.

    This line coverage report is in the `lcov
    <http://ltp.sourceforge.net/coverage/lcov.php>` format, so it can be used
    to generate HTML reports.
    """

    help = 'Generates a line coverage report. Requires that the binary has ' \
           'compiled with debug information and that the source code is '    \
           'available'

    def handle(self, *args, **options):
        target_path = self._project_desc['target_path']
        target_name = self._project_desc['target']

        # Get the translation block coverage information
        addr_counts = self._get_addr_coverage(target_name)
        if not addr_counts:
            raise CommandError('No translation block information found')

        file_line_info = line_info.get_file_line_coverage(target_path, addr_counts)
        lcov_info_path = self._save_coverage_info(file_line_info)

        if options.get('html', False):
            lcov_html_dir = self._gen_html(lcov_info_path)
            return 'Line coverage saved to %s. An HTML report is available in %s' % (lcov_info_path, lcov_html_dir)

        return 'Line coverage saved to %s' % lcov_info_path

    def _get_addr_coverage(self, target_name):
        """
        Extract address coverage from the JSON file(s) generated by the
        ``TranslationBlockCoverage`` plugin.

        Note that these addresses are an over-approximation of addresses
        actually executed because they are generated by extrapolating between
        the translation block start and end addresses. This doesn't actually
        matter, because if the address doesn't correspond to a line number in
        the DWARF information then it will just be ignored.

        Args:
            target_name: Name of the analysis target file.

        Returns:
            A dictionary mapping (over-approximated) instruction addresses
            executed by S2E to the number of times they were executed.
        """
        logger.info('Generating translation block coverage information')

        tb_coverage_files = get_tb_files(self.project_path('s2e-last'))
        addr_counts = {}

        # Get the number of times each address was executed by S2E
        for tb_coverage_file in tb_coverage_files:
            tb_coverage_data = parse_tb_file(tb_coverage_file, target_name)
            if not tb_coverage_data:
                continue

            for start_addr, end_addr, _ in tb_coverage_data:
                for addr in xrange(start_addr, end_addr):
                    addr_counts[addr] = addr_counts.get(addr, 0) + 1

        return addr_counts

    def _save_coverage_info(self, file_line_info):
        """
        Save the line coverage information in lcov format.

        The lcov format is described here:
        http://ltp.sourceforge.net/coverage/lcov/geninfo.1.php

        Args:
            file_line_info: The file line dictionary created by
                            ``_get_file_line_coverage``.

        Returns:
            The file path where the line coverage information was written to.
        """
        lcov_path = self.project_path('s2e-last', 'coverage.info')

        logger.info('Writing line coverage to %s', lcov_path)

        with open(lcov_path, 'w') as f:
            f.write('TN:\n')
            for src_file in file_line_info.keys():

                # Leave Windows paths alone, don't strip any missing ones.
                if '\\' in src_file:
                    abs_src_path = src_file
                else:
                    abs_src_path = os.path.realpath(src_file)

                    # TODO: genhtml has an option to ignore missing files,
                    # maybe it's better to keep them here
                    if not os.path.isfile(abs_src_path):
                        logger.warning('Cannot find source file \'%s\'. '
                                       'Skipping...', abs_src_path)
                        continue

                num_non_zero_lines = 0
                num_instrumented_lines = 0

                f.write('SF:%s\n' % abs_src_path)
                for line, count in file_line_info[src_file].items():
                    f.write('DA:%d,%d\n' % (line, count))

                    if count != 0:
                        num_non_zero_lines += 1
                    num_instrumented_lines += 1
                f.write('LH:%d\n' % num_non_zero_lines)
                f.write('LF:%d\n' % num_instrumented_lines)
                f.write('end_of_record\n')

        return lcov_path

    # TODO: support Windows paths on Linux
    def _gen_html(self, lcov_info_path):
        """
        Generate an LCOV HTML report.

        Returns the directory containing the HTML report.
        """
        from sh import genhtml, ErrorReturnCode

        lcov_html_dir = self.project_path('s2e-last', 'lcov')
        try:
            genhtml(lcov_info_path, output_directory=lcov_html_dir,
                    _out=sys.stdout, _err=sys.stderr, _fg=True)
        except ErrorReturnCode as e:
            raise CommandError(e)

        return lcov_html_dir