'''
Generic communication tasks. 

All remote calls are inline deferred callbacks. This allows them to be
easily chained together and fired asynchronously. 

Since calls are started with task.react, each method must take a reactor as its 
first parameter. 

Adding the defaultCallbacks decorator prints the result of the operation on 
success or failure. All failed calls return an exception which should be 
suitable for printing. 
'''

from twisted.internet import defer
from twisted.internet import reactor

from pdtools.coms.client import RpcClient
from pdtools.lib.output import out

import ast


###############################################################################
# Default Callbacks
###############################################################################

def defaultCallbacks(f):
    ''' 
    Wrap the API call in default handlers which print results. Optional 
    params are used to turn off specific handlers
    '''
    def w(*args, **kwargs):
        return f(*args, **kwargs).addCallbacks(printSuccess, printFailure)

    return w


def printSuccess(r):
    if isinstance(r, list):
        for x in r:
            print x
    else:
        print r


def printFailure(r):
    print 'Operation Failed!'
    print r


###############################################################################
# Generic Functionality
###############################################################################

@defaultCallbacks
@defer.inlineCallbacks
def logs(reactor, host, port):
    ''' Connect to the named device and ask for logs. '''
    client = RpcClient(host, port, 'internal')
    res = yield client.log()

    # comes back raw from the file, have to convert back to dics
    converted = [ast.literal_eval(x) for x in res.strip().split('\n')]
    for a in [out.messageToString(x) for x in converted]:
        print a
    # print formatted
    defer.returnValue('Done')


@defaultCallbacks
@defer.inlineCallbacks
def echo(reactor, host, port):
    client = RpcClient(host, port, 'internal')
    res = yield client.echo('Hello!')
    defer.returnValue(res)