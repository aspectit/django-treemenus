import re
from django.utils.functional import wraps
from django.contrib import admin
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.contrib.admin.util import unquote
from django.utils.translation import ugettext as _
from django.utils.encoding import force_unicode
from django.conf.urls.defaults import patterns
from django.core import urlresolvers
from django.core.exceptions import PermissionDenied
from django import forms

from treemenus.models import Menu, MenuItem
from treemenus.utils import get_parent_choices, MenuItemChoiceField, move_item_or_clean_ranks






class MenuItemAdmin(admin.ModelAdmin):
    ''' This class is used as a proxy by MenuAdmin to manipulate menu items. It should never be registered. '''
    def __init__(self, model, admin_site, menu):
        super(MenuItemAdmin, self).__init__(model, admin_site)
        self._menu = menu
    
    def delete_view(self, request, object_id, extra_context=None):
        if request.method == 'POST': # The user has already confirmed the deletion.
            # Delete and return to menu page
            ignored_response = super(MenuItemAdmin, self).delete_view(request, object_id, extra_context)
            return HttpResponseRedirect("../../../")
        else:
            # Show confirmation page
            return super(MenuItemAdmin, self).delete_view(request, object_id, extra_context)

    def save_model(self, request, obj, form, change):
        obj.menu = self._menu
        obj.save()

    def response_add(self, request, obj, post_url_continue='../%s/'):
        response = super(MenuItemAdmin, self).response_add(request, obj, post_url_continue)
        if request.POST.has_key("_continue"):
            return response
        elif request.POST.has_key("_addanother"):
            return HttpResponseRedirect(request.path)
        elif request.POST.has_key("_popup"):
            return response
        else:
            return HttpResponseRedirect("../../")

    def response_change(self, request, obj):
        response =  super(MenuItemAdmin, self).response_change(request, obj)
        if request.POST.has_key("_continue"):
            return HttpResponseRedirect(request.path)
        elif request.POST.has_key("_addanother"):
            return HttpResponseRedirect("../add/")
        elif request.POST.has_key("_saveasnew"):
            return HttpResponseRedirect("../%s/" % obj._get_pk_val())
        else:
            return HttpResponseRedirect("../../")

    def get_form(self, request, obj=None, **kwargs):
        Form = super(MenuItemAdmin, self).get_form(request, obj, **kwargs)
        class MyMenuItemForm(Form):
            def clean_named_url(self):
                data = self.cleaned_data.get('named_url')
                try:
                    if data:
                        urlresolvers.reverse(data)
                except urlresolvers.NoReverseMatch:
                    raise forms.ValidationError(u'This is not a valid URL.')
                else:
                    return data
        Form = MyMenuItemForm
        choices = get_parent_choices(self._menu, obj)
        Form.base_fields['parent'] = MenuItemChoiceField(choices=choices)
        return Form

class MenuAdmin(admin.ModelAdmin):
    menu_item_admin_class = MenuItemAdmin
    
    def __call__(self, request, url):
        ''' DEPRECATED!! More recent versions of Django use the get_urls method instead.
            Overriden to route extra URLs.
        '''
        if url:
            if url.endswith('items/add'):
                return self.add_menu_item(request, unquote(url[:-10]))
            if url.endswith('items'):
                return HttpResponseRedirect('../')
            match = re.match('^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)$', url)
            if match:
                return self.edit_menu_item(request, match.group('menu_pk'), match.group('menu_item_pk'))
            match = re.match('^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/delete$', url)
            if match:
                return self.delete_menu_item(request, match.group('menu_pk'), match.group('menu_item_pk'))
            match = re.match('^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/history$', url)
            if match:
                return self.history_menu_item(request, match.group('menu_pk'), match.group('menu_item_pk'))
            match = re.match('^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/move_up$', url)
            if match:
                return self.move_up_item(request, match.group('menu_pk'), match.group('menu_item_pk'))
            match = re.match('^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/move_down$', url)
            if match:
                return self.move_down_item(request, match.group('menu_pk'), match.group('menu_item_pk'))
        return super(MenuAdmin, self).__call__(request, url)
    
    def get_urls(self):
        urls = super(MenuAdmin, self).get_urls()
        my_urls = patterns('',
            (r'^(?P<menu_pk>[-\w]+)/items/add/$', self.admin_site.admin_view(self.add_menu_item)),
            (r'^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/$', self.admin_site.admin_view(self.edit_menu_item)),
            (r'^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/delete/$', self.admin_site.admin_view(self.delete_menu_item)),
            (r'^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/history/$', self.admin_site.admin_view(self.history_menu_item)),
            (r'^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/move_up/$', self.admin_site.admin_view(self.move_up_item)),
            (r'^(?P<menu_pk>[-\w]+)/items/(?P<menu_item_pk>[-\w]+)/move_down/$', self.admin_site.admin_view(self.move_down_item)),
        )
        return my_urls + urls
    
    def get_object_with_change_permissions(self, request, model, obj_pk):
        ''' Helper function that returns a menu/menuitem if it exists and if the user has the change permissions '''
        try:
            obj = model._default_manager.get(pk=obj_pk)
        except model.DoesNotExist:
            # Don't raise Http404 just yet, because we haven't checked
            # permissions yet. We don't want an unauthenticated user to be able
            # to determine whether a given object exists.
            obj = None
        if not self.has_change_permission(request, obj):
            raise PermissionDenied
        if obj is None:
            raise Http404('%s object with primary key %r does not exist.' % (model.__name__, escape(obj_pk)))
        return obj

    def add_menu_item(self, request, menu_pk):
        ''' Custom view '''
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menuitem_admin = self.menu_item_admin_class(MenuItem, self.admin_site, menu)
        return menuitem_admin.add_view(request, extra_context={ 'menu': menu })

    def edit_menu_item(self, request, menu_pk, menu_item_pk):
        ''' Custom view '''
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menu_item_admin = self.menu_item_admin_class(MenuItem, self.admin_site, menu)
        return menu_item_admin.change_view(request, menu_item_pk, extra_context={ 'menu': menu })

    def delete_menu_item(self, request, menu_pk, menu_item_pk):
        ''' Custom view '''
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menu_item_admin = self.menu_item_admin_class(MenuItem, self.admin_site, menu)
        return menu_item_admin.delete_view(request, menu_item_pk, extra_context={ 'menu': menu })

    def history_menu_item(self, request, menu_pk, menu_item_pk):
        ''' Custom view '''
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menu_item_admin = self.menu_item_admin_class(MenuItem, self.admin_site, menu)
        return menu_item_admin.history_view(request, menu_item_pk, extra_context={ 'menu': menu })

    def move_down_item(self, request, menu_pk, menu_item_pk):
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menu_item = self.get_object_with_change_permissions(request, MenuItem, menu_item_pk)
        
        if menu_item.rank < menu_item.siblings().count():
            move_item_or_clean_ranks(menu_item, 1)
            msg = _('The menu item "%s" was moved successfully.') % force_unicode(menu_item)
        else:
            msg = _('The menu item "%s" is not allowed to move down.') % force_unicode(menu_item)
        request.user.message_set.create(message=msg)
        return HttpResponseRedirect('../../../')
    
    def move_up_item(self, request, menu_pk, menu_item_pk):
        menu = self.get_object_with_change_permissions(request, Menu, menu_pk)
        menu_item = self.get_object_with_change_permissions(request, MenuItem, menu_item_pk)
        
        if menu_item.rank > 0:
            move_item_or_clean_ranks(menu_item, -1)
            msg = _('The menu item "%s" was moved successfully.') % force_unicode(menu_item)
        else:
            msg = _('The menu item "%s" is not allowed to move up.') % force_unicode(menu_item)
        request.user.message_set.create(message=msg)
        return HttpResponseRedirect('../../../')


admin.site.register(Menu, MenuAdmin)
