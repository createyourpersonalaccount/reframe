import abc
import os

import reframe.core.fields as fields
from reframe.core.exceptions import BuildSystemError


class BuildSystem:
    """The abstract base class of any build system.

    Concrete build systems inherit from this class and must override the
    :func:`emit_build_commands` abstract function.
    """

    #: The C compiler to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the compiler defined in the current programming environment will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    cc  = fields.StringField('cc', allow_none=True)

    #: The C++ compiler to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the compiler defined in the current programming environment will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    cxx = fields.StringField('cxx', allow_none=True)

    #: The Fortran compiler to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the compiler defined in the current programming environment will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    ftn = fields.StringField('ftn', allow_none=True)

    #: The CUDA compiler to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the compiler defined in the current programming environment will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    nvcc = fields.StringField('nvcc', allow_none=True)

    #: The C compiler flags to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the corresponding flags defined in the current programming environment
    #: will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    cflags = fields.TypedListField('cflags', str, allow_none=True)

    #: The preprocessor flags to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the corresponding flags defined in the current programming environment
    #: will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    cppflags = fields.TypedListField('cppflags', str, allow_none=True)

    #: The C++ compiler flags to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the corresponding flags defined in the current programming environment
    #: will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    cxxflags = fields.TypedListField('cxxflags', str, allow_none=True)

    #: The Fortran compiler flags to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the corresponding flags defined in the current programming environment
    #: will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    fflags  = fields.TypedListField('fflags', str, allow_none=True)

    #: The linker flags to be used.
    #: If set to :class:`None` and :attr:`flags_from_environ` is :class:`True`,
    #: the corresponding flags defined in the current programming environment
    #: will be used.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    ldflags = fields.TypedListField('ldflags', str, allow_none=True)

    #: Set compiler and compiler flags from the current programming environment
    #: if not specified otherwise.
    #:
    #: :type: :class:`bool`
    #: :default: :class:`True`
    flags_from_environ = fields.BooleanField('flags_from_environ')

    def __init__(self):
        self.cc  = None
        self.cxx = None
        self.ftn = None
        self.nvcc = None
        self.cflags = None
        self.cxxflags = None
        self.cppflags = None
        self.fflags  = None
        self.ldflags = None
        self.flags_from_environ = True

    @abc.abstractmethod
    def emit_build_commands(self, environ):
        """Return the list of commands for building using this build system.

        The build commands may always assume to be issued from the top-level
        directory of the code that is to be built.

        :arg environ: The programming environment for which to emit the build
           instructions.
           The framework passes here the current programming environment.
        :type environ: :class:`reframe.core.environments.ProgEnvironment`
        :raises: :class:`BuildSystemError` in case of errors when generating
          the build instructions.

        .. note::
            This method is relevant only to developers of new build systems.
        """

    def _resolve_flags(self, flags, environ, allow_none=True):
        _flags = getattr(self, flags)
        if _flags is not None:
            return _flags

        if self.flags_from_environ:
            return getattr(environ, flags)

        return None

    def _fix_flags(self, flags):
        # FIXME: That's a necessary workaround to the fact the environment
        # defines flags as strings, but here as lists of strings. Should be
        # removed as soon as setting directly the flags in an environment will
        # be disabled.
        if isinstance(flags, str):
            return flags.split()
        else:
            return flags

    def _cc(self, environ):
        return self._resolve_flags('cc', environ, False)

    def _cxx(self, environ):
        return self._resolve_flags('cxx', environ, False)

    def _ftn(self, environ):
        return self._resolve_flags('ftn', environ, False)

    def _nvcc(self, environ):
        return self._resolve_flags('nvcc', environ, False)

    def _cppflags(self, environ):
        return self._fix_flags(self._resolve_flags('cppflags', environ))

    def _cflags(self, environ):
        return self._fix_flags(self._resolve_flags('cflags', environ))

    def _cxxflags(self, environ):
        return self._fix_flags(self._resolve_flags('cxxflags', environ))

    def _fflags(self, environ):
        return self._fix_flags(self._resolve_flags('fflags', environ))

    def _ldflags(self, environ):
        return self._fix_flags(self._resolve_flags('ldflags', environ))


class Make(BuildSystem):
    """A build system for compiling codes using ``make``.

    The generated build command has the following form:

    .. code::

      make -j [N] [-f MAKEFILE] [-C SRCDIR] CC='X' CXX='X' FC='X' NVCC='X' CPPFLAGS='X' CFLAGS='X' CXXFLAGS='X' FFLAGS='X' LDFLAGS='X' OPTIONS

    The compiler and compiler flags variables will only be passed if they are
    not :class:`None`.
    Their value is determined by the corresponding attributes of
    :class:`BuildSystem`.
    If you want to completely disable passing these variables to the ``make``
    invocation, you should make sure not to set any of the correspoding
    attributes and set also the :attr:`BuildSystem.flags_from_environ` flag to
    :class:`False`.
    """

    #: Append these options to the ``make`` invocation.
    #: This variable is also useful for passing variables or targets to ``make``.
    #:
    #: :type: :class:`list[str]`
    #: :default: ``[]``
    options = fields.TypedListField('options', str)

    #: Instruct build system to use this Makefile.
    #: This option is useful when having non-standard Makefile names.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    makefile = fields.StringField('makefile', allow_none=True)

    #: The top-level directory of the code.
    #:
    #: This is set automatically by the framework based on the
    #: :attr:`reframe.core.pipeline.RegressionTest.sourcepath` attribute.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    srcdir = fields.StringField('srcdir', allow_none=True)

    #: Limit concurrency for ``make`` jobs.
    #: This attribute controls the ``-j`` option passed to ``make``.
    #: If not :class:`None`, ``make`` will be invoked as ``make -j
    #: max_concurrency``.
    #: Otherwise, it will invoked as ``make -j``.
    #:
    #: :type: integer
    #: :default: :class:`None`
    max_concurrency = fields.IntegerField('max_concurrency', allow_none=True)

    def __init__(self):
        super().__init__()
        self.options = []
        self.makefile = None
        self.srcdir = None
        self.max_concurrency = None

    def emit_build_commands(self, environ):
        cmd_parts = ['make']
        if self.makefile:
            cmd_parts += ['-f %s' % self.makefile]

        if self.srcdir:
            cmd_parts += ['-C %s' % self.srcdir]

        cmd_parts += ['-j']
        if self.max_concurrency is not None:
            cmd_parts += [str(self.max_concurrency)]

        cc = self._cc(environ)
        cxx = self._cxx(environ)
        ftn = self._ftn(environ)
        nvcc = self._nvcc(environ)
        cppflags = self._cppflags(environ)
        cflags   = self._cflags(environ)
        cxxflags = self._cxxflags(environ)
        fflags   = self._fflags(environ)
        ldflags  = self._ldflags(environ)
        if cc is not None:
            cmd_parts += ["CC='%s'" % cc]

        if cxx is not None:
            cmd_parts += ["CXX='%s'" % cxx]

        if ftn is not None:
            cmd_parts += ["FC='%s'" % ftn]

        if nvcc is not None:
            cmd_parts += ["NVCC='%s'" % nvcc]

        if cppflags is not None:
            cmd_parts += ["CPPFLAGS='%s'" % ' '.join(cppflags)]

        if cflags is not None:
            cmd_parts += ["CFLAGS='%s'" % ' '.join(cflags)]

        if cxxflags is not None:
            cmd_parts += ["CXXFLAGS='%s'" % ' '.join(cxxflags)]

        if fflags is not None:
            cmd_parts += ["FFLAGS='%s'" % ' '.join(fflags)]

        if ldflags is not None:
            cmd_parts += ["LDFLAGS='%s'" % ' '.join(ldflags)]

        if self.options:
            cmd_parts += self.options

        return [' '.join(cmd_parts)]


class SingleSource(BuildSystem):
    """A build system for compiling a single source file.

    The generated build command will have the following form:

    .. code::

      COMP CPPFLAGS XFLAGS SRCFILE -o EXEC LDFLAGS

    - ``COMP`` is the required compiler for compiling ``SRCFILE``.
      This build system will automatically detect the programming language of
      the source file and pick the correct compiler.
      See also the :attr:`SingleSource.lang` attribute.
    - ``CPPFLAGS`` are the preprocessor flags and are passed to any compiler.
    - ``XFLAGS`` is any of ``CFLAGS``, ``CXXFLAGS`` or ``FFLAGS`` depending on
      the programming language of the source file.
    - ``SRCFILE`` is the source file to be compiled.
      This is set up automatically by the framework.
      See also the :attr:`SingleSource.srcfile` attribute.
    - ``EXEC`` is the executable to be generated.
      This is also set automatically by the framework.
      See also the :attr:`SingleSource.executable` attribute.
    - ``LDFLAGS`` are the linker flags.

    For CUDA codes, the language assumed is C++ (for the compilation flags) and
    the compiler used is :attr:`BuildSystem.nvcc`.

    """

    #: The source file to compile.
    #: This is automatically set by the framework based on the
    #: :attr:`reframe.core.pipeline.RegressionTest.sourcepath` attribute.
    #:
    #: :type: :class:`str` or :class:`None`
    srcfile = fields.StringField('srcfile', allow_none=True)

    #: The executable file to be generated.
    #:
    #: This is set automatically by the framework based on the
    #: :attr:`reframe.core.pipeline.RegressionTest.executable` attribute.
    #:
    #: :type: :class:`str` or :class:`None`
    executable = fields.StringField('executable', allow_none=True)

    #: The include path to be used for this compilation.
    #:
    #: All the elements of this list will be appended to the
    #: :attr:`BuildSystem.cppflags`, by prepending to each of them the ``-I``
    #: option.
    #:
    #: :type: :class:`list[str]`
    #: :default: ``[]``
    include_path = fields.TypedListField('include_path', str)

    #: The programming language of the file that needs to be compiled.
    #: If not specified, the build system will try to figure it out
    #: automatically based on the extension of the source file.
    #: The automatically detected extensions are the following:
    #:
    #:   - C: `.c`.
    #:   - C++: `.cc`, `.cp`, `.cxx`, `.cpp`, `.CPP`, `.c++` and `.C`.
    #:   - Fortran: `.f`, `.for`, `.ftn`, `.F`, `.FOR`, `.fpp`, `.FPP`, `.FTN`,
    #:     `.f90`, `.f95`, `.f03`, `.f08`, `.F90`, `.F95`, `.F03` and `.F08`.
    #:   - CUDA: `.cu`.
    #:
    #: :type: :class:`str` or :class:`None`
    lang = fields.StringField('lang', allow_none=True)

    def __init__(self):
        super().__init__()
        self.srcfile = None
        self.executable = None
        self.include_path = []
        self.lang = None

    def _auto_exec_name(self):
        return '%s.exe' % os.path.splitext(self.srcfile)[0]

    def emit_build_commands(self, environ):
        if not self.srcfile:
            raise BuildSystemError(
                'a source file is required when using the %s build system' %
                type(self).__name__)

        cc = self._cc(environ)
        cxx = self._cxx(environ)
        ftn = self._ftn(environ)
        nvcc = self._nvcc(environ)
        cppflags = self._cppflags(environ) or []
        cflags   = self._cflags(environ) or []
        cxxflags = self._cxxflags(environ) or []
        fflags   = self._fflags(environ)  or []
        ldflags  = self._ldflags(environ) or []

        # Adjust cppflags with the include directories
        # NOTE: We do not use the += operator on purpose, be cause we don't
        # want to change the original list passed by the user
        cppflags = cppflags + [*map(lambda d: '-I ' + d, self.include_path)]

        # Generate the executable
        executable = self.executable or self._auto_exec_name()

        # Prepare the compilation command
        lang = self.lang or self._guess_language(self.srcfile)
        cmd_parts = []
        if lang == 'C':
            if cc is None:
                raise BuildSystemError('I do not know how to compile a '
                                       'C program')

            cmd_parts += [cc, *cppflags, *cflags, self.srcfile,
                          '-o', executable, *ldflags]
        elif lang == 'C++':
            if cxx is None:
                raise BuildSystemError('I do not know how to compile a '
                                       'C++ program')

            cmd_parts += [cxx, *cppflags, *cxxflags, self.srcfile,
                          '-o', executable, *ldflags]
        elif lang == 'Fortran':
            if ftn is None:
                raise BuildSystemError('I do not know how to compile a '
                                       'Fortran program')

            cmd_parts += [ftn, *cppflags, *fflags, self.srcfile,
                          '-o', executable, *ldflags]
        elif lang == 'CUDA':
            if nvcc is None:
                raise BuildSystemError('I do not know how to compile a '
                                       'CUDA program')

            cmd_parts += [nvcc, *cppflags, *cxxflags, self.srcfile,
                          '-o', executable, *ldflags]
        else:
            BuildSystemError('could not guess language of file: %s' %
                             self.srcfile)

        return [' '.join(cmd_parts)]

    def _guess_language(self, filename):
        _, ext = os.path.splitext(filename)
        if ext in ['.c']:
            return 'C'

        if ext in ['.cc', '.cp', '.cxx', '.cpp', '.CPP', '.c++', '.C']:
            return 'C++'

        if ext in ['.f', '.for', '.ftn', '.F', '.FOR', '.fpp',
                   '.FPP', '.FTN', '.f90', '.f95', '.f03', '.f08',
                   '.F90', '.F95', '.F03', '.F08']:
            return 'Fortran'

        if ext in ['.cu']:
            return 'CUDA'


class CMake(BuildSystem):
    """A build system for compiling CMake-based projects.

    This build system will emit the following commands:

    1. Create a build directory if :attr:`builddir` is not :class:`None` and
       change to it.
    2. Invoke ``cmake`` to configure the project by setting the corresponding
       CMake flags for compilers and compiler flags.
    3. Issue ``make`` to compile the code.
    """

    #: The top-level directory of the code.
    #:
    #: This is set automatically by the framework based on the
    #: :attr:`reframe.core.pipeline.RegressionTest.sourcepath` attribute.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    srcdir = fields.StringField('srcdir', allow_none=True)

    #: The CMake build directory, where all the generated files will be placed.
    #:
    #: :type: :class:`str`
    #: :default: :class:`None`
    builddir = fields.StringField('builddir', allow_none=True)

    #: Additional configuration options to be passed to the CMake invocation.
    #:
    #: :type: :class:`list[str]`
    #: :default: ``[]``
    config_opts = fields.TypedListField('config_opts', str)

    def __init__(self):
        super().__init__()
        self.srcdir = None
        self.builddir = None
        self.config_opts = []
        self.max_concurrency = None

    def _combine_flags(self, cppflags, xflags):
        if cppflags is None:
            return xflags

        ret = list(cppflags)
        if xflags:
            ret += xflags

        return ret

    def emit_build_commands(self, environ):
        prepare_cmd = []
        if self.srcdir:
            prepare_cmd += ['cd %s' % self.srcdir]

        if self.builddir:
            prepare_cmd += ['mkdir -p %s' % self.builddir,
                            'cd %s' % self.builddir]

        cmake_cmd = ['cmake']
        cc = self._cc(environ)
        cxx = self._cxx(environ)
        ftn = self._ftn(environ)
        nvcc = self._nvcc(environ)
        cppflags = self._cppflags(environ)
        cflags   = self._combine_flags(cppflags, self._cflags(environ))
        cxxflags = self._combine_flags(cppflags, self._cxxflags(environ))
        fflags   = self._combine_flags(cppflags, self._fflags(environ))
        ldflags  = self._ldflags(environ)
        if cc is not None:
            cmake_cmd += ["-DCMAKE_C_COMPILER='%s'" % cc]

        if cxx is not None:
            cmake_cmd += ["-DCMAKE_CXX_COMPILER='%s'" % cxx]

        if ftn is not None:
            cmake_cmd += ["-DCMAKE_Fortran_COMPILER='%s'" % ftn]

        if nvcc is not None:
            cmake_cmd += ["-DCMAKE_CUDA_COMPILER='%s'" % nvcc]

        if cflags is not None:
            cmake_cmd += ["-DCMAKE_C_FLAGS='%s'" % ' '.join(cflags)]

        if cxxflags is not None:
            cmake_cmd += ["-DCMAKE_CXX_FLAGS='%s'" % ' '.join(cxxflags)]

        if fflags is not None:
            cmake_cmd += ["-DCMAKE_Fortran_FLAGS='%s'" % ' '.join(fflags)]

        if ldflags is not None:
            cmake_cmd += ["-DCMAKE_EXE_LINKER_FLAGS='%s'" % ' '.join(ldflags)]

        if self.config_opts:
            cmake_cmd += self.config_opts

        if self.builddir:
            cmake_cmd += [os.path.relpath('.', self.builddir)]
        else:
            cmake_cmd += ['.']

        make_cmd = ['make -j']
        if self.max_concurrency is not None:
            make_cmd += [str(self.max_concurrency)]

        return prepare_cmd + [' '.join(cmake_cmd), ' '.join(make_cmd)]


class BuildSystemField(fields.TypedField):
    """A field representing a build system.

    You may either assign an instance of :class:`BuildSystem` or a string
    representing the name of the concrete class of a build system.
    """

    def __init__(self, fieldname, allow_none=False):
        super().__init__(fieldname, BuildSystem, allow_none)

    def __set__(self, obj, value):
        if isinstance(value, str):
            try:
                value = globals()[value]()
            except KeyError:
                raise ValueError('unknown build system: %s' % value) from None

        super().__set__(obj, value)
