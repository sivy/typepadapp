from django.http import HttpResponseBadRequest

def ajax_required(f):
    """
    AJAX request required decorator
    via http://www.djangosnippets.org/snippets/771/
    
    Use this on all AJAX views to help prevent
    XSS attacks.
    """    
    def wrap(request, *args, **kwargs):
            if not request.is_ajax():
                return HttpResponseBadRequest()
            return f(request, *args, **kwargs)
    wrap.__doc__=f.__doc__
    wrap.__name__=f.__name__
    return wrap