#
# Copyright SAS Institute
#
#  Licensed under the Apache License, Version 2.0 (the License);
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#
#
# This module is designed to connect to SAS from python, providing a natural python style interface.
# it provides base functionality, data access and processing, and includes analytics and ODS results.
# There is a configuration file named sascfg.py in the saspy package used to configure connections
# to SAS. Currently supported methods are STDIO, connecting to a local (same machine) Linux SAS using
# stdio methods (fork, exec, and pipes). The is also support for running STDIO over SSH, which can 
# connect to a remote linux SAS via passwordless ssh. The ssh method cannot currently support interrupt
# handling, as the local STDIO method can. An interrupt on this method can only terminate the SAS process;
# you'll be prompted to terminate or wait for completion. The third method is HTTP, which can connect
# to SAS Viya via the Compute Servie, a restful micro service in the Viya system.
#
# Each of these connection methods (access methods) are handled by their own IO module. This main
# module determines which IO module to use based upon the configuration chosen at runtime. More
# IO modules can be seamlessly plugged in, if needed, in the future.
#
# The expected use is to simply import this package and establish a SAS session, then use the methods:
#
# import saspy
# sas = saspy.SASsession()
# sas.[have_at_it]()
#

import os
from pdb import set_trace as bp
import saspy.sascfg as SAScfg
import logging

try:
    import saspy.sasiostdio as sasiostdio
    import saspy.sasioiom   as sasioiom
    running_on_win = False

except:
    running_on_win = True

import saspy.sasiohttp  as sasiohttp
from saspy.sasstat    import *
from saspy.sasets     import *
from saspy.sasml      import *
from saspy.sasqc      import *
from saspy.sasutil    import *
from saspy.sasresults import *

try:
    from IPython.display import HTML
    from IPython.display import display as DISPLAY
except ImportError:
    pass


class SASconfig:
    """
    This object is not intended to be used directly. Instantiate a SASsession object instead
    """

    def __init__(self, **kwargs):
        configs = []
        self._kernel = kwargs.get('kernel', None)
        self.valid = True
        self.mode = ''

        # GET Config options
        try:
            self.cfgopts = getattr(SAScfg, "SAS_config_options")
        except:
            self.cfgopts = {}

        # GET Config names
        configs = getattr(SAScfg, "SAS_config_names")

        cfgname = kwargs.get('cfgname', '')

        if len(cfgname) == 0:
            if len(configs) == 0:
                print("No SAS Configuration names found in saspy.sascfg")
                self.valid = False
                return
            else:
                if len(configs) == 1:
                    cfgname = configs[0]
                    if self._kernel == None:
                        print("Using SAS Config named: " + cfgname)
                else:
                    cfgname = self._prompt(
                        "Please enter the name of the SAS Config you wish to run. Available Configs are: " +
                        str(configs) + " ")

        while cfgname not in configs:
            cfgname = self._prompt(
                "The SAS Config name specified was not found. Please enter the SAS Config you wish to use. Available Configs are: " +
                str(configs) + " ")

        self.name = cfgname
        cfg = getattr(SAScfg, cfgname)

        ip = cfg.get('ip', '')
        ssh = cfg.get('ssh', '')
        path = cfg.get('saspath', '')
        java = cfg.get('java', '')

        if len(java) > 0:
            self.mode = 'IOM'
        elif len(ip) > 0:
            self.mode = 'HTTP'
        elif len(ssh) > 0:
            self.mode = 'SSH'
        elif len(path) > 0:
            self.mode = 'STDIO'
        else:
            self.valid = False

    def _prompt(self, prompt, pw=False):
        if self._kernel is None:
            if not pw:
                try:
                    return input(prompt)
                except KeyboardInterrupt:
                    return ''
            else:
                try:
                    return getpass.getpass(prompt)
                except KeyboardInterrupt:
                    return ''
        else:
            try:
                return self._kernel._input_request(prompt, self._kernel._parent_ident, self._kernel._parent_header,
                                                   password=pw)
            except KeyboardInterrupt:
                return ''


class SASsession:
    """
    The SASsession object is the main object to instantiate and provides access to the rest of the functionality.
    cfgname - value in SAS_config_names List of the sascfg.py file
    kernel  - None - internal use when running the SAS_kernel notebook
    results - Type of tabular results to return. default is 'Pandas', other options are 'HTML or 'TEXT'

    For the STDIO IO Module
    saspath - overrides saspath Dict entry of cfgname in sascfg.py file
    options - overrides options Dict entry of cfgname in sascfg.py file

    and for running STDIO over passwordless ssh
    ssh     - full path of the ssh command; /usr/bin/ssh for instance
    host    - host name of the remote machine

    and for the HTTP IO module to connect to SAS Viya
    ip      - host address
    port    - port; the code Defaults this to 80 (the Compute Services default port)
    context - context name defined on the compute service
    options - SAS options to include in the start up command line
    user    - user name to authenticate with
    pw      - password to authenticate with

    and for the IOM IO module to connect to SAS9 via Java IOM
    ip      - host address
    port    - port; the code Defaults this to 80 (the Compute Services default port)
    context - context name defined on the compute service
    options - SAS options to include in the start up command line
    omruser - user name to authenticate with
    omrpw   - password to authenticate with
    """

    # def __init__(self, cfgname: str ='', kernel: '<SAS_kernel object>' =None, saspath :str ='', options: list =[]) -> '<SASsession object>':
    def __init__(self, **kwargs) -> '<SASsession object>':
        self._loaded_macros = False
        self._obj_cnt = 0
        self.nosub = False
        self.sascfg = SASconfig(**kwargs)
        self.batch = False
        self.results = kwargs.get('results', 'Pandas')

        if not self.sascfg.valid:
            return

        if self.sascfg.mode in ['STDIO', 'SSH', '']:
            if not running_on_win:
                self._io = sasiostdio.SASsessionSTDIO(sascfgname=self.sascfg.name, sb=self, **kwargs)
            else:
                print(
                "Cannot use STDIO I/O module on Windows. No SASsession established. Choose an HTTP SASconfig definition")
                return
        elif self.sascfg.mode == 'HTTP':
            self._io = sasiohttp.SASsessionHTTP(sascfgname=self.sascfg.name, sb=self, **kwargs)

        elif self.sascfg.mode == 'IOM':
            self._io = sasioiom.SASsessionIOM(sascfgname=self.sascfg.name, sb=self, **kwargs)


def __del__(self):
    return self._io.__del__()


def _objcnt(self):
    self._obj_cnt += 1
    return '%04d' % self._obj_cnt


def _startsas(self):
    return self._io._startsas()


def _endsas(self):
    return self._io._endsas()


def _getlog(self, **kwargs):
    return self._io._getlog(**kwargs)


def _getlst(self, **kwargs):
    return self._io._getlst(**kwargs)


def _getlsttxt(self, **kwargs):
    return self._io._getlsttxt(**kwargs)


def _asubmit(self, code, result):
    if results == '':
        if self.results.upper() == 'PANDAS':
            results = 'HTML'
        else:
            results = self.results

    return self._io._asubmit(code, result)


def submit(self, code: str, results

: str = '', prompt: dict = []) -> dict:
'''
This method is used to submit any SAS code. It returns the Log and Listing as a python dictionary.
code    - the SAS statements you want to execute
results - format of results, HTLML and TEXT is the alternative
prompt  - dict of names:flags to prompt for; create marco variables (used in submitted code), then keep or delete
          The keys are the names of the macro variables and the boolean flag is to either hide what you type and delete
          the macros, or show what you type and keep the macros (they will still be available later)
          for example (what you type for pw will not be displayed, user and dsname will):

          results_dict = sas.submit(
             """
             libname tera teradata server=teracop1 user=&user pw=&pw;
             proc print data=tera.&dsname (obs=10); run;
             """ ,
             prompt = {'user': False, 'pw': True, 'dsname': False}
             )

Returns - a Dict containing two keys:values, [LOG, LST]. LOG is text and LST is 'results' (HTML or TEXT)

NOTE: to view HTML results in the ipykernel, issue: from IPython.display import HTML  and use HTML() instead of print()
i.e,: results = sas.submit("data a; x=1; run; proc print;run')
      print(results['LOG'])
      HTML(results['LST'])
'''
if self.nosub:
    return dict(LOG=code, LST='')

if results == '':
    if self.results.upper() == 'PANDAS':
        results = 'HTML'
    else:
        results = self.results

return self._io.submit(code, results, prompt)


def saslog(self) ->


'The SAS Log for the session':
'''
this method is used to get the current, full contents of the SASLOG
'''
return self._io.saslog()


def teach_me_SAS(self, nosub: bool

):
'''
nosub - bool. True means don't submit the code, print it out so I can see what the SAS code would be.
              False means run normally - submit the code.
'''
self.nosub = nosub


def set_batch(self, batch: bool

):
'''
This method sets the batch attribute for the SASsession object; it stays in effect untill changed. For methods that just
display results like SASdata object methods (head, tail, hist, series) and SASresult object results, you can set 'batch'
to true to get the results back directly so you can write them to files or whatever you want to do with them. This is intended
for use in python batch scripts so you can still get ODS XML5 results and save them to files, which you couldn't otherwise do for
these methods. When running interactivly, the expectation is that you want to have the results directly rendered, but you can
run this way too; get the objects display them yourself and/or write them to somewhere. When true, you get the same dictionary
returned as from the SASsession.submit() method.

batch - set the default result type for this SASsession. True = return dict([LOG, LST]. False = display LST to screen.
'''
self.batch = batch


def set_results(self, results: str

):
'''
This method set the results attribute for the SASsession object; it stays in effect till changed
results - set the default result type for this SASdata object. 'Pandas' or 'HTML' or 'TEXT'.
'''
self.results = results


def exist(self, table: str, libref

: str = "") -> bool:
'''
table  - the name of the SAS Data Set
libref - the libref for the Data Set, defaults to WORK, or USER if assigned

Returns True it the Data Set exists and False if it does not
'''
return self._io.exist(table, libref)


def sasstat(self) ->


'<SASstat object>':
'''
This methods creates a SASstat object which you can use to run various analytics. See the sasstat.py module.
'''
if not self._loaded_macros:
    self._loadmacros()
    self._loaded_macros = True

return SASstat(self)


def sasets(self) ->


'<SASets object>':
'''
This methods creates a SASets object which you can use to run various analytics. See the sasets.py module.
'''
if not self._loaded_macros:
    self._loadmacros()
    self._loaded_macros = True

return SASets(self)


def sasml(self) ->


'<SASml object>':
'''
This methods creates a SASML object which you can use to run various analytics. See the sasml.py module.
'''
if not self._loaded_macros:
    self._loadmacros()
    self._loaded_macros = True

return SASml(self)


def sasqc(self) ->


'<SASqc object>':
'''
This methods creates a SASqc object which you can use to run various analytics. See the sasqc.py module.
'''
if not self._loaded_macros:
    self._loadmacros()
    self._loaded_macros = True

return SASqc(self)


def sasutil(self) ->


'<SASutil object>':
'''
This methods creates a SASutil object which you can use to run various analytics. See the sasutil.py module.
'''
if not self._loaded_macros:
    self._loadmacros()
    self._loaded_macros = True

return SASutil(self)


def _loadmacros(self):
    macro_path = os.path.dirname(os.path.realpath(__file__))
    fd = os.open(macro_path + '/' + 'libname_gen.sas', os.O_RDONLY)
    code = b'options nosource;\n'
    code += os.read(fd, 32767)
    code += b'\noptions source;'

    self._io._asubmit(code.decode(), results='text')
    os.close(fd)


def sasdata(self, table: str, libref

: str = '', results: str = '', dsopts: dict = {})  -> '<SASdata object>':
'''
This method creates a SASdata object for the SAS Data Set you specify
table   - the name of the SAS Data Set
libref  - the libref for the Data Set, defaults to WORK, or USER if assigned
results - format of results, SASsession.results is default, Pandas, HTML and TEXT are the valid options
dsopts - a dictionary containing any of the following SAS data set options(where, drop, keep, obs, firstobs):
         where is a sting, keep and drop are strings or list of strings. obs and first obs are numbers - either string or int
         {'where'    : 'msrp < 20000 and make = "Ford"'
          'keep'     : 'msrp enginesize Cylinders Horsepower Weight'
          'drop'     : ['msrp', 'enginesize', 'Cylinders', 'Horsepower', 'Weight']
          'obs'      :  10
          'firstobs' : '12'
         }
'''
if results == '':
    results = self.results
sd = SASdata(self, libref, table, results, dsopts)
if not self.exist(sd.table, sd.libref):
    if not self.batch:
        print(
        "Table " + sd.libref + '.' + sd.table + " does not exist. This SASdata object will not be useful until the data set is created.")
return sd


def saslib(self, libref: str, engine

: str = ' ', path: str = '', options: str = ' ') -> 'The LOG showing the assignment of the libref':
'''
This method is used to assign a libref. The libref is then available to be used in the SAS session.
libref  - the libref for be assigned
engine  - the engine name used to access the SAS Library (engine defaults to BASE, per SAS)
path    - path to the library (for engines that take a path parameter)
options - other engine or engine supervisor options
'''
code = "libname " + libref + " " + engine + " "
if len(path) > 0:
    code += " '" + path + "' "
code += options + ";"

if self.nosub:
    print(code)
else:
    ll = self._io.submit(code, "text")
    if self.batch:
        return ll['LOG'].rsplit(";*\';*\";*/;\n")[0]
    else:
        print(ll['LOG'].rsplit(";*\';*\";*/;\n")[0])


def datasets(self, libref: str = ''

) -> 'The LOG showing the output':
'''
This method is used to query a libref. The results show information about the libref including members.
libref  - the libref to query
'''
code = "proc datasets"
if libref:
    code += " dd=" + libref
code += "; quit;"

if self.nosub:
    print(code)
else:
    ll = self._io.submit(code, "text")
    if self.batch:
        return ll['LOG'].rsplit(";*\';*\";*/;\n")[0]
    else:
        print(ll['LOG'].rsplit(";*\';*\";*/;\n")[0])


def read_csv(self, file: str, table

: str = '_csv', libref: str = '', results: str = '') -> '<SASdata object>':
'''
This method will import a csv file into a SAS Data Set and return the SASdata object referring to it.
file    - either the OS filesystem path of the file, or HTTP://... for a url accessible file
table   - the name of the SAS Data Set to create
libref  - the libref for the SAS Data Set being created. Defaults to WORK, or USER if assigned
results - format of results, SASsession.results is default, HTML or TEXT are the alternatives
'''
if results == '':
    results = self.results
self._io.read_csv(file, table, libref, self.nosub)

if self.exist(table, libref):
    return SASdata(self, libref, table, results)
else:
    return None


def write_csv(self, file: str, table

: str, libref: str = '', dsopts: dict = {}) -> 'The LOG showing the results of the step':
'''
This method will export a SAS Data Set to a file in CSV format.
file    - the OS filesystem path of the file to be created (exported from the SAS Data Set)
table   - the name of the SAS Data Set you want to export to a CSV file
libref  - the libref for the SAS Data Set.
'''
log = self._io.write_csv(file, table, libref, self.nosub, dsopts)
if not self.batch:
    print(log)
else:
    return log


def df2sd(self, df: '<Pandas Data Frame object>', table

: str = '_df', libref: str = '', results: str = '') -> '<SASdata object>':
'''
This is an alias for 'dataframe2sasdata'. Why type all that?
df      - Pandas Data Frame to import to a SAS Data Set
table   - the name of the SAS Data Set to create
libref  - the libref for the SAS Data Set being created. Defaults to WORK, or USER if assigned
results - format of results, SASsession.results is default, HTML or TEXT are the alternatives
'''
return self.dataframe2sasdata(df, table, libref, results)


def dataframe2sasdata(self, df: '<Pandas Data Frame object>', table

: str = '_df', libref: str = '', results: str = '') -> '<SASdata object>':
'''
This method imports a Pandas Data Frame to a SAS Data Set, returning the SASdata object for the new Data Set.
df      - Pandas Data Frame to import to a SAS Data Set
table   - the name of the SAS Data Set to create
libref  - the libref for the SAS Data Set being created. Defaults to WORK, or USER if assigned
results - format of results, SASsession.results is default, HTML or TEXT are the alternatives
'''
if results == '':
    results = self.results
if self.nosub:
    print("too complicated to show the code, read the source :), sorry.")
    return None
else:
    self._io.dataframe2sasdata(df, table, libref)

if self.exist(table, libref):
    return SASdata(self, libref, table, results)
else:
    return None


def sd2df(self, table: str, libref

: str = '', dsopts: dict = {}, ** kwargs) -> '<Pandas Data Frame object>':
'''
This is an alias for 'sasdata2dataframe'. Why type all that?
sd      - SASdata object that refers to the Sas Data Set you want to export to a Pandas Data Frame
table   - the name of the SAS Data Set you want to export to a Pandas Data Frame
libref  - the libref for the SAS Data Set.
'''
return self.sasdata2dataframe(table, libref, dsopts, **kwargs)


def sasdata2dataframe(self, table: str, libref

: str = '', dsopts: dict = {}, ** kwargs) -> '<Pandas Data Frame object>':
'''
This method exports the SAS Data Set to a Pandas Data Frame, returning the Data Frame object.
table   - the name of the SAS Data Set you want to export to a Pandas Data Frame
libref  - the libref for the SAS Data Set.
'''
if self.exist(table, libref) == 0:
    print('The SAS Data Set ' + libref + '.' + table + ' does not exist')
    return None

if self.nosub:
    print("too complicated to show the code, read the source :), sorry.")
    return None
else:
    return self._io.sasdata2dataframe(table, libref, dsopts, **kwargs)


def _dsopts(self, dsopts):
    '''
    This method builds out data set optiond clause for this SASdata object: '(where= , keeep=, obs=, ...)'
    '''
    opts = ''

    if len(dsopts):
        for key in dsopts:
            if len(str(dsopts[key])):
                if key == 'where':
                    opts += 'where=(' + dsopts[key] + ') '
                elif key == 'drop':
                    opts += 'drop='
                    if isinstance(dsopts[key], list):
                        for var in dsopts[key]:
                            opts += var + ' '
                    else:
                        opts += dsopts[key] + ' '
                elif key == 'keep':
                    opts += 'keep='
                    if isinstance(dsopts[key], list):
                        for var in dsopts[key]:
                            opts += var + ' '
                    else:
                        opts += dsopts[key] + ' '
                elif key == 'obs':
                    opts += 'obs=' + str(dsopts[key]) + ' '
                elif key == 'firstobs':
                    opts += 'firstobs=' + str(dsopts[key]) + ' '
        if len(opts):
            opts = '(' + opts + ')'
    return opts


class SASdata:
    def __init__(self, sassession, libref, table, results='', dsopts={}):

        self.sas = sassession
        self.logger = logging.getLogger(__name__)

        if results == '':
            results = sassession.results

        failed = 0
        if results.upper() == "HTML":
            try:
                from IPython.display import HTML
            except:
                failed = 1

            if failed and not self.sas.batch:
                self.HTML = 0
            else:
                self.HTML = 1
        else:
            self.HTML = 0

        if len(libref):
            self.libref = libref
        else:
            if self.sas.exist(table, libref='user'):
                self.libref = 'USER'
            else:
                self.libref = 'WORK'

            # hack till the bug gets fixed
            if self.sas.sascfg.mode == 'HTTP':
                self.libref = 'WORK'

        self.table = table
        self.dsopts = dsopts
        self.results = results

    def set_results(self, results:
        str

    ):
    '''
    This method set the results attribute for the SASdata object; it stays in effect till changed
    results - set the default result type for this SASdata object. 'Pandas' or 'HTML' or 'TEXT'.
    '''
    if results.upper() == "HTML":
        self.HTML = 1
    else:
        self.HTML = 0
    self.results = results


def _is_valid(self):
    if self.sas.exist(self.table, self.libref):
        return None
    else:
        msg = "The SAS Data Set that this SASdata object refers to, " + self.libref + '.' + self.table + ", does not exist in this SAS session at this time."
        ll = {'LOG': msg, 'LST': msg}
        return ll


def _returnPD(self, code, tablename, **kwargs):
    libref = 'work'
    if 'libref' in kwargs:
        libref = kwargs['libref']
    self.sas._io.submit(code)
    if isinstance(tablename, str):
        pd = self.sas._io.sasdata2dataframe(tablename, libref)
        self.sas._io.submit("proc delete data=%s.%s; run;" % (libref, tablename))
    elif isinstance(tablename, list):
        pd = dict()
        for t in tablename:
            # strip leading '_' from names and capitalize for dictionary labels
            pd[t.replace('_', '').capitalize()] = self.sas._io.sasdata2dataframe(t, libref)
            self.sas._io.submit("proc delete data=%s.%s; run;" % (libref, t))
    else:
        raise SyntaxError("The tablename must be a string or list %s was submitted" % str(type(tablename)))

    return pd


def _dsopts(self):
    '''
    This method builds out data set optiond clause for this SASdata object: '(where= , keeep=, obs=, ...)'
    '''
    return self.sas._dsopts(self.dsopts)


def where(self, where: str

) -> '<SASdata object>':
'''
This method returns a clone of the SASdata object, with the where attribute set. The original SASdata object is not affected.
where - the where clause to apply

'''
sd = SASdata(self.sas, self.libref, self.table, dsopts=dict(self.dsopts))
sd.HTML = self.HTML
sd.dsopts['where'] = where
return sd


def head(self, obs=5):
    '''
    display the first n rows of a table
    obs - the number of rows of the table that you want to display. The default is 5

    '''
    topts = dict(self.dsopts)
    topts['obs'] = obs
    code = "proc print data=" + self.libref + '.' + self.table + self.sas._dsopts(topts) + ";run;"

    if self.sas.nosub:
        print(code)
        return

    if self.results.upper() == 'PANDAS':
        code = "data _head ; set %s.%s(obs=%s); run;" % (self.libref, self.table, obs)
        return self._returnPD(code, '_head')
    else:
        ll = self._is_valid()
        if self.HTML:
            if not ll:
                ll = self.sas._io.submit(code)
            if not self.sas.batch:
                DISPLAY(HTML(ll['LST']))
            else:
                return ll
        else:
            if not ll:
                ll = self.sas._io.submit(code, "text")
            if not self.sas.batch:
                print(ll['LST'])
            else:
                return ll


def tail(self, obs=5):
    '''
    display the last n rows of a table
    obs - the number of rows of the table that you want to display. The default is 5

    '''
    # code = "%put lastobs=%sysfunc(attrn(%sysfunc(open("+self.libref+'.'+self.table+")),NOBS)) tom;"
    code = "proc sql;select count(*) into :lastobs from " + self.libref + '.' + self.table + self._dsopts() + ";%put lastobs=&lastobs tom;"

    nosub = self.sas.nosub
    self.sas.nosub = False

    le = self._is_valid()
    if not le:
        ll = self.sas.submit(code, "text")

        lastobs = ll['LOG'].rpartition("lastobs=")
        lastobs = lastobs[2].partition(" tom")
        lastobs = int(lastobs[0])
    else:
        lastobs = obs

    firstobs = lastobs - (obs - 1)
    if firstobs < 1:
        firstobs = 1

    topts = dict(self.dsopts)
    topts['obs'] = lastobs
    topts['firstobs'] = firstobs

    code = "proc print data=" + self.libref + '.' + self.table + self.sas._dsopts(topts) + ";run;"

    self.sas.nosub = nosub
    if self.sas.nosub:
        print(code)
        return

    if self.results.upper() == 'PANDAS':
        code = "data _tail ; set %s.%s(firstobs=%s obs=%s); run;" % (self.libref, self.table, firstobs, lastobs)
        return self._returnPD(code, '_tail')
    else:
        if self.HTML:
            if not le:
                ll = self.sas._io.submit(code)
            else:
                ll = le
            if not self.sas.batch:
                DISPLAY(HTML(ll['LST']))
            else:
                return ll
        else:
            if not le:
                ll = self.sas._io.submit(code, "text")
            else:
                ll = le
            if not self.sas.batch:
                print(ll['LST'])
            else:
                return ll


def partition(self, var='', fraction=.7, seed=9878, kfold=1, out=None, singleOut=True):
    """
    Partion a sas data object using SRS sampling or if a variable is specified then stratifiying with respect to that variable
    """
    # bp()
    # loop through for k folds cross-validation
    i = 1
    # initialize code string so that loops work
    code = ''
    # Make sure kfold was an integer
    try:
        k = int(kfold)
    except ValueError:
        print("Kfold must be an integer")
    if out is None:
        out_table = self.table
        out_libref = self.libref
    elif not isinstance(out, str):
        out_table = out.table
        out_libref = out.libref
    else:
        try:
            out_table = out.split('.')[1]
            out_libref = out.split('.')[0]
        except IndexError:
            out_table = out
            out_libref = 'work'
    while i <= k:
        # get the list of variables
        if k == 1:
            code += "proc hpsample data=%s.%s%s out=%s.%s%s samppct=%s seed=%s Partition;\n" % (
            self.libref, self.table, self._dsopts(), out_libref, out_table, self._dsopts(), fraction * 100, seed)
        else:
            seed += 1
            code += "proc hpsample data=%s.%s%s out=%s.%s%s samppct=%s seed=%s partition PARTINDNAME=_cvfold%s;\n" % (
            self.libref, self.table, self._dsopts(), out_libref, out_table, self._dsopts(), fraction * 100, seed, i)

        # Get variable info for stratified sampling
        if len(var) > 0:
            if i == 1:
                num_string = """
                    proc contents data={0}.{1};
                        ods output variables=_charlist;
                    run;
                    data _charlist;
                        set _charlist;
                        where Type='Num';
                        keep Variable;
                    run;
                    """
                # ignore teach_me_SAS mode to run contents
                nosub = self.sas.nosub
                self.sas.nosub = False
                self.sas.submit(num_string.format(self.libref, self.table + self._dsopts()))
                numlist1 = list(self.sas.sasdata2dataframe('_charlist', libref='WORK').values.flatten())
                self.sas.submit("proc delete data=work._charlist; run;")
                self.sas.nosub = nosub

                # check if var is in numlist1
                if isinstance(var, str):
                    tlist = var.split()
                elif isinstance(var, list):
                    tlist = var
                else:
                    raise SyntaxError("var must be a string or list you submitted: %s" % str(type(var)))
            if set(numlist1).isdisjoint(tlist):
                if isinstance(var, str):
                    code += "class _character_;\ntarget %s;\nvar _numeric_;\n" % var
                else:
                    code += "class _character_;\ntarget %s;\nvar _numeric_;\n" % " ".join(var)
            else:
                varlist = [x for x in numlist1 if x not in tlist]
                varlist.extend(["_cvfold%s" % j for j in range(1, i) if k > 1 and i > 1])
                code += "class %s _character_;\ntarget %s;\nvar %s;\n" % (var, var, " ".join(varlist))

        else:
            code += "class _character_;\nvar _numeric_;\n"
        code += "run;\n"
        i += 1
    # split_code is used if singleOut is False it generates the needed SAS code to break up the kfold parition set.
    split_code = ''
    if not singleOut:
        split_code += 'DATA '
        for j in range(1, k + 1):
            split_code += "\t%s.%s%s_train(drop=_Partind_ _cvfold:)\n" % (out_libref, out_table, j)
            split_code += "\t%s.%s%s_score(drop=_Partind_ _cvfold:)\n" % (out_libref, out_table, j)
        split_code += ';\n \tset %s.%s;\n' % (out_libref, out_table)
        for z in range(1, k + 1):
            split_code += "\tif _cvfold%s = 1 then output %s.%s%s_train;\n" % (z, out_libref, out_table, z)
            split_code += "\telse output %s.%s%s_score;\n" % (out_libref, out_table, z)
        split_code += 'run;'
    runcode = True
    if self.sas.nosub:
        print(code + '\n\n' + split_code)
        runcode = False
    ll = self._is_valid()
    if ll:
        runcode = False
    if runcode:
        ll = self.sas.submit(code + split_code, "text")
        elog = []
        for line in ll['LOG'].splitlines():
            if line.startswith('ERROR'):
                elog.append(line)
        if len(elog):
            raise RuntimeError("\n".join(elog))
        if not singleOut:
            outTableList = []
            for j in range(1, k + 1):
                outTableList.extend([self.sas.sasdata(out_table + str(z) + "_train", out_libref, dsopts=self._dsopts()),
                                     self.sas.sasdata(out_table + str(z) + "_score", out_libref,
                                                      dsopts=self._dsopts())])
            return outTableList
        if out:
            if not isinstance(out, str):
                return out
            else:
                return self.sas.sasdata(out_table, out_libref, self.results)
        else:
            return self


def contents(self):
    '''
    display metadata about the table. size, number of rows, columns and their data type ...

    '''
    code = "proc contents data=" + self.libref + '.' + self.table + self._dsopts() + ";run;"

    if self.sas.nosub:
        print(code)
        return

    ll = self._is_valid()
    if self.results.upper() == 'PANDAS':
        code = "proc contents data=%s.%s ;" % (self.libref, self.table)
        code += "ods output Attributes=_attributes;"
        code += "ods output EngineHost=_EngineHost;"
        code += "ods output Variables=_Variables;"
        code += "ods output Sortedby=_Sortedby;"
        code += "run;"
        return self._returnPD(code, ['_attributes', '_EngineHost', '_Variables', '_Sortedby'])

    else:
        if self.HTML:
            if not ll:
                ll = self.sas._io.submit(code)
            if not self.sas.batch:
                DISPLAY(HTML(ll['LST']))
            else:
                return ll
        else:
            if not ll:
                ll = self.sas._io.submit(code, "text")
            if not self.sas.batch:
                print(ll['LST'])
            else:
                return ll


def columnInfo(self):
    """
    display metadata about the table, size, number of rows, columns and their data type
    """
    code = "proc contents data=" + self.libref + '.' + self.table + ' ' + self._dsopts() + ";ods select Variables;run;"

    if self.sas.nosub:
        print(code)
        return

    if self.results.upper() == 'PANDAS':
        code = "proc contents data=%s.%s ;ods output Variables=_variables ;run;" % (self.libref, self.table)
        return self._returnPD(code, '_variables')

    else:
        ll = self._is_valid()
        if self.HTML:
            if not ll:
                ll = self.sas._io.submit(code)
            if not self.sas.batch:
                DISPLAY(HTML(ll['LST']))
            else:
                return ll
        else:
            if not ll:
                ll = self.sas._io.submit(code, "text")
            if not self.sas.batch:
                print(ll['LST'])
            else:
                return ll


def describe(self):
    '''
    display descriptive statistics for the table; summary statistics.

    '''
    return self.means()

    def info(self):
        m = self.means()
        c = self.columnInfo()
        p1 = m[['Variable', 'N','NMiss']]
        p2 = c[['Variable', 'Type']]
        info = pd.merge(p1, p2, on='Variable', how='outer')
        return(info)

    def means(self):
        '''
        display descriptive statistics for the table; summary statistics. This is an alias for 'describe'

        '''
        code  = "proc means data="+self.libref+'.'+self.table+self._dsopts()+" n nmiss median mean std min p25 p50 p75 max;run;"
        
        if self.sas.nosub:
           print(code)
           return


        if self.results.upper() == 'PANDAS':
            code = "proc means data=%s.%s stackodsoutput n nmiss median mean std min p25 p50 p75 max; ods output Summary=_summary; run;" %(self.libref, self.table)
            return self._returnPD(code, '_summary')
        else:
            if not ll:
                ll = self.sas._io.submit(code, "text")
            if not self.sas.batch:
                print(ll['LST'])
            else:
                return ll


    def sort(self, by: str, out: 'str or sas data object' = '', ** kwargs) -> '<SASdata object>':
      """
      This method will sort the SAS Data Set
      by  - REQUIRED variable to sort by (BY <DESCENDING> variable-1 <<DESCENDING> variable-2 ...>;)
      out - OPTIONAL takes either a string 'libref.table' or 'table' which will go to WORK or USER if assigned or a sas data object'' will sort in place if allowed
      returns this SASdata object if out= not specified, or a new SASdata object for out= when specified

      Examples:
      1. wkcars.sort('type')
      2. wkcars2 = sas.sasdata('cars2')
         wkcars.sort('cylinders', wkcars2)
      3. cars2=cars.sort('DESCENDING origin', out='foobar')
      4. cars.sort('type').head()
      5. stat_results = stat.reg(model='horsepower = Cylinders EngineSize', by='type', data=wkcars.sort('type'))
      6. stat_results2 = stat.reg(model='horsepower = Cylinders EngineSize', by='type', data=wkcars.sort('type','work.cars'))

      """
      outstr = ''
      options = ''
      if out:
          if isinstance(out, str):
              fn = out.partition('.')
              if fn[1] == '.':
                  libref = fn[0]
                  table = fn[2]
                  outstr = "out=%s.%s" % (libref, table)
              else:
                  libref = ''
                  table = fn[0]
                  outstr = "out=" + table
          else:
              libref = out.libref
              table = out.table
              outstr = "out=%s.%s" % (out.libref, out.table)

    def assessModel(self, target: str, prediction: str, nominal: bool =True, event: str ='', **kwargs):
        """
        This method will calculate assessment measures using the SAS AA_Model_Eval Macro used for SAS Enterprise Miner.
        Not all datasets can be assessed. This is designed for scored data that includes a target and prediction columns
        TODO: add code example of build, score, and then assess
        :param target: string that represents the target variable in the data
        :param prediction: string that represetnt the prediction column in the data
        :param nominal: boolean to indicate if the Target Variable is nominal because the assessment measures are different.
        :param sortOrder: string of either DESC or ASC which indicates which value of the target variable is the event vs non-event
        :param kwargs:
        :return: sas result object
        """
        # submit autocall macro
        self.sas.submit("%aamodel;")
        objtype = "datastep"
        objname = '{s:{c}^{n}}'.format(s=self.table[:3], n=3, c='_') + self.sas._objcnt()  # translate to a libname so needs to be less than 8
        code = "%macro proccall(d);\n"

        # build parameters
        score_table = str(self.libref + '.' + self.table)
        binstats = str(objname + '.' + "ASSESSMENTSTATISTICS")
        out = str(objname + '.' + "ASSESSMENTBINSTATISTICS")
        level = 'interval'
        #var = 'P_' + target
        if nominal:
            level = 'class'
            # the user didn't specify the event for a nominal Give them the possible choices
            try:
                if len(event) < 1:
                    raise Exception(event)
            except Exception:
                print("No event was specified for a nominal target. Here are possible options:\n")
                event_code  = "proc hpdmdb data=%s.%s classout=work._DMDBCLASSTARGET(keep=name nraw craw level frequency nmisspercent);" % (self.libref, self.table)
                event_code += "\nclass %s ; \nrun;" % target
                event_code += "data _null_; set work._DMDBCLASSTARGET; where ^(NRAW eq . and CRAW eq '') and lowcase(name)=lowcase('%s');" % target
                ec = self.sas.submit(event_code)
                HTML(ec['LST'])

        if nominal:
            code +="%%aa_model_eval(DATA=%s, TARGET=%s, VAR=%s, level=%s, BINSTATS=%s, bins=100, out=%s,  EVENT=%s);" \
                   % (score_table, target, prediction , level, binstats, out, event)
        else:
            code +="%%aa_model_eval(DATA=%s, TARGET=%s, VAR=%s, level=%s, BINSTATS=%s, bins=100, out=%s);" \
                   % (score_table, target, prediction, level, binstats, out)
        code += "run; quit; %mend;\n"
        code += "%%mangobj(%s,%s,%s);" % (objname, objtype, self.table)
        rename_char = """
        data {0};
            set {0};
            if level in ("INTERVAL", "INT") then do;
                rename  _sse_ = SumSquaredError
                        _div_ = Divsor
                        _ASE_ = AverageSquaredError
                        _RASE_ = RootAverageSquaredError
                        _MEANP_ = MeanPredictionValue
                        _STDP_ = StandardDeviationPrediction
                        _CVP_ = CoefficientVariationPrediction;
            end;
            else do;
                rename  CR = MaxClassificationRate
                        KSCut = KSCutOff
                        CRDEPTH =  MaxClassificationDepth
                        MDepth = MedianClassificationDepth
                        MCut  = MedianEventDetectionCutOff
                        CCut = ClassificationCutOff
                        _misc_ = MisClassificationRate;
            end;
        run;

        """
        code += rename_char.format(binstats)
        # TODO: add graphics code here to return to the SAS results object
        """
        # Debug block
        debug={'name': name,
               'score_table': score_table,
               'target': target,
               'var': var,
               'nominals': nominals,
               'level': level,
               'binstats': binstats,
               'out':out}
        print(debug.items())
        """
        if self.sas.nosub:
           print(code)
           return

        ll=self.sas.submit(code, 'text')
        obj1 = SASProcCommons._objectmethods(self, objname)
        return SASresults(obj1, self.sas, objname, self.sas.nosub, ll['LOG'])

    def to_csv(self, file: str) -> 'The LOG showing the results of the step':
        '''
        This method will export a SAS Data Set to a file in CSV format.
        file    - the OS filesystem path of the file to be created (exported from this SAS Data Set)
        '''
        ll = self._is_valid()
        if ll:
           if not self.sas.batch:
              print(ll['LOG'])
           else:
              return ll
        else:
           return self.sas.write_csv(file, self.table, self.libref, self.dsopts)

    def to_frame(self, **kwargs) -> '<Pandas Data Frame object>':
      '''
      Export this SAS Data Set to a Pandas Data Frame
      '''
      return self.to_df(**kwargs)

    def to_df(self, **kwargs) -> '<Pandas Data Frame object>':
      '''
      Export this SAS Data Set to a Pandas Data Frame
      '''
      ll = self._is_valid()
      if ll:
        print(ll['LOG'])
        return None
      else:
          return self.sas.sasdata2dataframe(self.table, self.libref, self.dsopts, **kwargs)

    def heatmap(self, x: str, y: str, options: str = '', title: str = '', label: str = '') -> 'a heatmap plot of the (numeric) variables you chose':
      """
      Documentation link: http://support.sas.com/documentation/cdl/en/grstatproc/67909/HTML/default/viewer.htm#n0w12m4cn1j5c6n12ak64u1rys4w.htm
      :param x: x variable
      :param y: y variable
      :param options: display options (string)
      :param title: graph title
      :param label:
      :return:
      """
      code = "proc sgplot data=%s.%s%s;" % (self.libref, self.table, self._dsopts())
      if len(options):
          code += "\n\theatmap x=%s y=%s / %s;" % (x, y, options)
      else:
          code += "\n\theatmap x=%s y=%s;" % (x, y)

      if len(label) > 0:
          code += " LegendLABEL='" + label + "'"
      code += ";\n"
      if len(title) > 0:
          code += "\ttitle '%s';\n" % title
      code += "run;\ntitle;"

      if self.sas.nosub:
          print(code)
          return

      ll = self._is_valid()
      if not ll:
          html = self.HTML
          self.HTML = 1
          ll = self.sas._io.submit(code)
          self.HTML = html
      if not self.sas.batch:
          DISPLAY(HTML(ll['LST']))
      else:
          return ll

    def hist(self, var: str, title: str = '', label: str = '') -> 'a histogram plot of the (numeric) variable you chose':
      '''
      This method requires a numeric column (use the contents method to see column types) and generates a histogram.
      var   - the NUMERIC variable (column) you want to plot
      title - an optional Title for the chart
      label - LegendLABEL= value for sgplot
      '''
      code = "proc sgplot data=" + self.libref + '.' + self.table + self._dsopts()
      code += ";\n\thistogram " + var + " / scale=count"
      if len(label) > 0:
          code += " LegendLABEL='" + label + "'"
      code += ";\n"
      if len(title) > 0:
          code += '\ttitle "' + title + '";\n'
      code += "\tdensity " + var + ';\nrun;\n' + 'title \"\";'

      if self.sas.nosub:
          print(code)
          return

      ll = self._is_valid()
      if not ll:
          html = self.HTML
          self.HTML = 1
          ll = self.sas._io.submit(code)
          self.HTML = html
      if not self.sas.batch:
          DISPLAY(HTML(ll['LST']))
      else:
          return ll

    def top(self, var: str, n: int = 10, order: str = 'freq', title: str = '') -> 'a frequency analysis of a variable':
      """
      This method finds the most common levels of a variable
      var   - the CHAR variable (column) you want to count
      n     - the top N to be displayed (defaults to 10)
      order - default to most common use order='data' to get then in alphbetic order
      title - an optional Title for the chart
      label - LegendLABEL= value for sgplot
      """
      code = "proc freq data=%s.%s%s order=%s noprint;" % (self.libref, self.table, self._dsopts(), order)
      code += "\n\ttables %s / out=tmpFreqOut;" % var
      code += "\nrun;"
      if len(title) > 0:
          code += '\ttitle "' + title + '";\n'
      code += "proc print data=tmpFreqOut(obs=%s); \nrun;" % n
      code += 'title \"\";'

      if self.sas.nosub:
          print(code)
          return

      ll = self._is_valid()
      if self.results.upper() == 'PANDAS':
          code = "proc freq data=%s.%s order=%s noprint;" % (self.libref, self.table, order)
          code += "\n\ttables %s / out=tmpFreqOut;" % var
          code += "\nrun;"
          code += "\ndata tmpFreqOut; set tmpFreqOut(obs=%s); run;" % n
          return self._returnPD(code, 'tmpFreqOut')
      else:
          if self.HTML:
              if not ll:
                  ll = self.sas._io.submit(code)
              if not self.sas.batch:
                  DISPLAY(HTML(ll['LST']))
              else:
                  return ll
          else:
              if not ll:
                  ll = self.sas._io.submit(code, "text")
              if not self.sas.batch:
                  print(ll['LST'])
              else:
                  return ll


    def bar(self, var: str, title: str = '', label: str = '') -> 'a barchart plot of the (numeric) variable you chose':
      '''
      This method requires a numeric column (use the contents method to see column types) and generates a histogram.
      var   - the CHAR variable (column) you want to plot
      title - an optional Title for the chart
      label - LegendLABEL= value for sgplot
      '''
      code = "proc sgplot data=" + self.libref + '.' + self.table + self._dsopts()
      code += ";\n\tvbar " + var + " ; "
      if len(label) > 0:
          code += " LegendLABEL='" + label + "'"
      code += ";\n"
      if len(title) > 0:
          code += '\ttitle "' + title + '";\n'
      code += 'title \"\";'
      code += 'run;'

      if self.sas.nosub:
          print(code)
          return

      ll = self._is_valid()
      if not ll:
          html = self.HTML
          self.HTML = 1
          ll = self.sas._io.submit(code)
          self.HTML = html
      if not self.sas.batch:
          DISPLAY(HTML(ll['LST']))
      else:
          return ll

    def series(self, x: str, y: list, title: str = '') -> 'a line plot of the x,y coordinates':
      '''
      This method plots a series of x,y coordinates. You can provide a list of y columns for multiple line plots.
      x     - the x axis variable; generally a time or continuous variable.
      y     - the y axis variable(s), you can specify a single column or a list of columns
      title - an optional Title for the chart
      '''
      code = "proc sgplot data=" + self.libref + '.' + self.table + self._dsopts() + ";\n"
      if len(title) > 0:
          code += '\ttitle "' + title + '";\n'

      if type(y) == list:
          num = len(y)
      else:
          num = 1
          y = [y]

      for i in range(num):
          code += "\tseries x=" + x + " y=" + y[i] + ";\n"

      code += 'run;\n' + 'title \"\";'

      if self.sas.nosub:
          print(code)
          return

      ll = self._is_valid()
      if not ll:
          html = self.HTML
          self.HTML = 1
          ll = self.sas._io.submit(code)
          self.HTML = html
      if not self.sas.batch:
          DISPLAY(HTML(ll['LST']))
      else:
          return ll

if __name__ == "__main__":
    startsas()

    submit(sys.argv[1], "text")

    print(_getlog())
    print(_getlsttxt())

    endsas()