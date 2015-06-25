###################################################################
# Copyright 2013-2015 All Rights Reserved
# Authors: The Paradrop Team
###################################################################

import traceback
from paradrop.lib.utils.output import out, logPrefix

from paradrop.backend.exc import plangraph

'''
    This module contains the methods required to generate and act upon
    execution plans.

    An execution plan is a set of operations that must be performed
    to update a Chute from some old state into the new state provided
    by the API server.

    All plans that are generated are function pointers, as in no actual
    operations are performed during the generation process.
'''


def generatePlans(update):
    """
    For an update object provided this function references the updateModuleList which lets all exc
    modules determine if they need to add functions to change the state of the system when new 
    chutes are added to the OS.

    Returns: True in error, as in we should stop with this update plan
    """
    out.header('== %s Generating %r\n' % (logPrefix(), update))

    # Iterate through the list provided for this update type
    for mod in update.updateModuleList:
        if(mod.generatePlans(update)):
            return True
            


def aggregatePlans(update):
    """
        Takes the PlanMap provided which can be a combination of changes for multiple
        different chutes and it puts things into a sane order and removes duplicates where
        possible.

        This keeps things like reloading networking from happening twice if 2 chutes make changes.
        
        Returns:
            A new PlanMap that should be executed
    """
    out.header('== %s Aggregating plans\n' % logPrefix())
    # For now we just order the plans and return a new list
    update.plans.sort()

def executePlans(update):
    """
        Primary function that actually executes all the functions that were added to plans by all
        the exc modules. This function can heavily modify the OS/files/etc.. so the return value is
        very important.
        Returns:
            True in error : abortPlans function should be called
            False otherwise : everything is OK
    """
    out.header('== %s Executing plans %r\n' % (logPrefix(), update))
    # Finding the functions to call is actually done by a 'iterator' like function in the plangraph module
    while(True):
        # This function either returns None or a tuple just like generate added to it
        p = update.plans.getNextTodo()
        
        # No more to do?
        if(not p):
            break
        
        # Explode tuple otherwise
        ch, func, args = p
            
        try:
            # We are in a try-except block so if func isn't callable that will catch it
            skipme = func(args)
        
        except Exception as e2:
            out.err('!! %s Exception executing plan %r: %s\n%s\n' % (logPrefix(), update.plans, str(e2), traceback.format_exc()))
            update.responses.append({'exception': str(e2), 'traceback': traceback.format_exc()})
            return True
            
        # The functions we call here can return other functions, if they do these are functions that should
        # be skipped later on (for instance a set* function discovering it didn't change anything, later on
        # we shouldn't call the corresponding reload function)
        if(skipme):
            # These functions can return individual functions to skip, or a list of multiple functions 
            if (not isinstance(skipme, list)):
                skipme = [skipme]

            for skip in skipme:
                out.warn('** %s Identified a skipped function: %r\n' % (logPrefix(), skip))
                update.plans.registerSkip(skip)
    
    # Now we are done
    return False

def abortPlans(update):
    """
        This function should be called if one of the Plan objects throws an Exception.
        It takes the PlanMap argument and calls the getNextAbort function just like executePlans does with todoPlans.
        This dynamically generates an abort plan list based on what plans were originally executed.
        Returns:
            True in error : This is really bad
            False otherwise : we were able to restore system state back to before the executeplans function was called
    """
    out.header('== %s Aborting plans %r\n' % (logPrefix(), update.plans))
    sameError = False
    while(True):
        try:
            # This function either returns None or a tuple just like generate added to it
            p = update.plans.getNextAbort()
            
            # No more to do?
            if(not p):
                break
            
            # Explode tuple otherwise
            ch, func, args = p
            
            # We are in a try-except block so if func isn't callable that will catch it
            func(args)
            
            # If the func is called without exception then clear the @sameError flag for the next function call
            sameError = False

        except Exception as e:
            # Since we are running this in an infinite loop if a major function throws an error
            # we could loop forever, so check for the error, which is only reset at the end of the loop
            if(sameError):
                return True
            responseMessages.append({'exception': str(e), 'traceback': traceback.format_exc()})
            out.fatal('!! %s An abort function raised an exception!!! %r: %s\n%s\n' % (logPrefix(), update.plans, str(e), traceback.format_exc()))
            sameError = True
    
    # Getting here we assume the system state has been restored using our abort plan
    return False