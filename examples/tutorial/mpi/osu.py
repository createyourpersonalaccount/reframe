# Copyright 2016-2024 Swiss National Supercomputing Centre (CSCS/ETH Zurich)
# ReFrame Project Developers. See the top-level LICENSE file for details.
#
# SPDX-License-Identifier: BSD-3-Clause

import os
import reframe as rfm
import reframe.utility.typecheck as typ
import reframe.utility.sanity as sn


class fetch_osu_benchmarks(rfm.RunOnlyRegressionTest):
    descr = 'Fetch OSU benchmarks'
    version = variable(str, value='7.3')
    executable = 'wget'
    executable_opts = [
        f'http://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-{version}.tar.gz'  # noqa: E501
    ]
    local = True

    @sanity_function
    def validate_download(self):
        return sn.assert_eq(self.job.exitcode, 0)


class build_osu_benchmarks(rfm.CompileOnlyRegressionTest):
    descr = 'Build OSU benchmarks'
    build_system = 'Autotools'
    build_prefix = variable(str)
    osu_benchmarks = fixture(fetch_osu_benchmarks, scope='session')

    @run_before('compile')
    def prepare_build(self):
        tarball = f'osu-micro-benchmarks-{self.osu_benchmarks.version}.tar.gz'
        self.build_prefix = tarball[:-7]  # remove .tar.gz extension

        fullpath = os.path.join(self.osu_benchmarks.stagedir, tarball)
        self.prebuild_cmds = [
            f'cp {fullpath} {self.stagedir}',
            f'tar xzf {tarball}',
            f'cd {self.build_prefix}'
        ]
        self.build_system.max_concurrency = 8


class osu_base_test(rfm.RunOnlyRegressionTest):
    '''Base class of OSU benchmarks runtime tests'''

    valid_systems = ['*']
    valid_prog_environs = ['+mpi']
    num_tasks = 2
    num_tasks_per_node = 1
    osu_binaries = fixture(build_osu_benchmarks, scope='environment')
    kind = variable(str)
    benchmark = variable(str)
    metric = variable(typ.Str[r'latency|bandwidth'])

    @run_before('run')
    def prepare_run(self):
        self.executable = os.path.join(
            self.osu_binaries.stagedir,
            self.osu_binaries.build_prefix,
            'c', 'mpi', self.kind, self.benchmark
        )
        self.executable_opts = ['-x', '100', '-i', '1000']

    @sanity_function
    def validate_test(self):
        return sn.assert_found(r'^8', self.stdout)

    def _extract_metric(self, size):
        return sn.extractsingle(rf'^{size}\s+(\S+)', self.stdout, 1, float)

    @run_before('performance')
    def set_perf_vars(self):
        make_perf = sn.make_performance_function
        if self.metric == 'latency':
            self.perf_variables = {
                'latency': make_perf(self._extract_metric(8), 'us')
            }
        else:
            self.perf_variables = {
                'bandwidth': make_perf(self._extract_metric(1048576), 'MB/s')
            }


@rfm.simple_test
class osu_latency_test(osu_base_test):
    descr = 'OSU latency test'
    kind = 'pt2pt/standard'
    benchmark = 'osu_latency'
    metric = 'latency'
    executable_opts = ['-x', '3', '-i', '10']


@rfm.simple_test
class osu_bandwidth_test(osu_base_test):
    descr = 'OSU bandwidth test'
    kind = 'pt2pt/standard'
    benchmark = 'osu_bw'
    metric = 'bandwidth'
    executable_opts = ['-x', '3', '-i', '10']


@rfm.simple_test
class osu_allreduce_test(osu_base_test):
    descr = 'OSU Allreduce test'
    kind = 'collective/blocking'
    benchmark = 'osu_allreduce'
    metric = 'bandwidth'
    executable_opts = ['-m', '8', '-x', '3', '-i', '10']
