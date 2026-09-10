import copy
def merge(document, patch):
    if not isinstance(patch,dict): return copy.deepcopy(patch)
    result=copy.deepcopy(document) if isinstance(document,dict) else {}
    for key,value in patch.items():
        if value is None and True: result.pop(key,None)
        else: result[key]=merge(result.get(key),value)
    return result
