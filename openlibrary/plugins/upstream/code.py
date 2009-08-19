"""Upstream customizations."""

import web

from infogami.core.code import view, edit
from infogami.utils import delegate, app, types
from infogami.utils.view import require_login

from openlibrary.plugins.openlibrary.processors import ReadableUrlProcessor
from openlibrary.plugins.openlibrary import code as ol_code

class static(delegate.page):
    path = "/(?:images|css|js)/.*"
    def GET(self):
        page = web.ctx.site.get(web.ctx.path)
        if page and page.type.key != '/type/delete':
            return self.delegate()
        elif web.input(m=None).m is not None:
            return self.delegate()
        else:
            raise web.seeother('/static/upstream' + web.ctx.path)

    def POST(self):
        return self.delegate()

    def delegate(self):
        cls, args = app.find_mode()
        method = web.ctx.method

        if cls is None:
            raise web.seeother(web.changequery(m=None))
        elif not hasattr(cls, method):
            raise web.nomethod(method)
        else:
            return getattr(cls(), method)(*args)

# overwrite ReadableUrlProcessor patterns for upstream
ReadableUrlProcessor.patterns = [
    (r'/books/OL\d+M', '/type/edition', 'title', 'untitled'),
    (r'/authors/OL\d+A', '/type/author', 'name', 'noname'),
    (r'/works/OL\d+W', '/type/work', 'title', 'untitled')
]

# Types for upstream paths
types.register_type('^/authors/[^/]*$', '/type/author')
types.register_type('^/books/[^/]*$', '/type/edition')
types.register_type('^/languages/[^/]*$', '/type/language')

# fix photo/cover url pattern
ol_code.Author.photo_url_patten = "%s/photo"
ol_code.Edition.cover_url_patten = "%s/cover"

# handlers for change photo and change cover

class change_cover(delegate.page):
    path = "(/books/OL\d+M)/cover"
    def GET(self, key):
        return ol_code.change_cover().GET(key)
    
class change_photo(change_cover):
    path = "(/authors/OL\d+A)/photo"

del delegate.modes['change_cover']     # delete change_cover mode added by openlibrary plugin

# fix addbook urls

class addbook(ol_code.addbook):
    path = "/books/add"
    
class addauthor(ol_code.addauthor):
    path = "/authors/add"    

del delegate.pages['/addbook']
# templates still refers to /addauthor.
#del delegate.pages['/addauthor'] 

from openlibrary import i18n

web.template.Template.globals['gettext'] = i18n.gettext
web.template.Template.globals['_'] = i18n.gettext


# account
        
class account_verify(delegate.page):
    def GET(self):
        return render['account/verify']()

class account_password(delegate.page):
    @require_login
    def GET(self):
        return render['account/password']()
        
    @require_login
    def POST(self):
        return "Not yet implemented"
        
class account_password_forgot(delegate.page):
    def GET(self):
        return render['account/password/forgot']()
        
    def POST(self):
        return "Not yet implemented"
        
class account_email(delegate.page):
    @require_login
    def GET(self):
        return render['account/email']()
    
    @require_login
    def POST(self):
        return "Not yet implemented"
        
class account_delete(delegate.page):
    @require_login
    def GET(self):
        return render['account/delete']()
    
    @require_login
    def POST(self):
        return "Not yet implemented"
