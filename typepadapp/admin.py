# Copyright (c) 2009-2010 Six Apart Ltd.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of Six Apart Ltd. nor the names of its contributors may
#   be used to endorse or promote products derived from this software without
#   specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from django.contrib import admin

from typepadapp.models.auth import Token
from typepadapp.models.feedsub import Subscription

import random
from django.conf import settings
from urlparse import urlparse, urlunsplit
from django.core.urlresolvers import reverse

import urllib
from oauth import oauth

import typepad

from pprint import pprint

import logging
log = logging.getLogger(__name__)

class SubscriptionAdmin(admin.ModelAdmin):

    model = Subscription
    list_display = ('name', 'feeds_list', 'filters_list','url_id', 'verified')
    readonly_fields = ('secret',)

    def feeds_list(self, obj):
        return ', '.join(obj.feeds.split('\n'))
    feeds_list.short_description = 'Feeds'

    def filters_list(self, obj):
        return ', '.join(obj.filters.split('\n'))
    filters_list.short_description = 'Filters'

    def save_model(self, request, obj, form, change):
        log.info('handle changed subscription')
        if (change):
            log.debug('WILL: update subscription in typepad')
        else:
            log.debug('WILL: create subscription in typepad')
        
        ###
        # setup for pushing to typepad
        for setting in ('OAUTH_CONSUMER_KEY', 'OAUTH_CONSUMER_SECRET', 'OAUTH_GENERAL_PURPOSE_KEY',
                        'OAUTH_GENERAL_PURPOSE_SECRET'):
            if not hasattr(settings, setting):
                raise CommandError("%s setting is required" % setting)
        ###
        # setup endpoint
        try:
            typepad.client.endpoint = settings.BACKEND_URL
        except AttributeError:
            typepad.client.endpoint = 'https://api.typepad.com'

        ###
        # apply any TYPEPAD_COOKIES declared
        try:
            typepad.client.cookies.update(settings.TYPEPAD_COOKIES)
        except AttributeError:
            pass

        ###
        # Setup for OAuth authentication
        consumer = oauth.OAuthConsumer(settings.OAUTH_CONSUMER_KEY, settings.OAUTH_CONSUMER_SECRET)
        token = oauth.OAuthToken(settings.OAUTH_GENERAL_PURPOSE_KEY, settings.OAUTH_GENERAL_PURPOSE_SECRET)
        backend = urlparse(typepad.client.endpoint)
        typepad.client.add_credentials(consumer, token, domain=backend[1])
        
        # collect data for sync to typepad
        feed_idents = obj.feeds.split("\n")
        
        if len(feed_idents) == 0:
            raise CommandError("At least one feed URL parameter is required")
        
        filters = str(obj.filters).split("\n") or []

        current_site = Site.objects.get_current()
        domain = current_site.domain
        if domain == 'example.com':
            raise CommandError("Your Django 'sites' have not been configured")
        
        secret = ''.join(random.choice(ascii_letters+digits) for x in xrange(0,20))
        
        # generate a verification token
        verify_token = ''.join(random.choice(ascii_letters+digits) for x in xrange(0,20))
        if (not change):
            # new object
            # save to typepad
            try:
                callback_path = reverse('typepadapp.views.feedsub.callback', kwargs={'sub_id': str(s.id)})
                callback_url = urlunsplit(('http', domain, callback_path, '', ''))

                application = typepad.Application.get_by_id(settings.APPLICATION_ID)
                resp = application.create_external_feed_subscription(
                    callback_url=callback_url,
                    feed_idents=feed_idents,
                    filter_rules=filters,
                    secret=secret,
                    verify_token=verify_token)
            except Exception, exc:
                resp = None
                log.exception(exc)

            if resp:
                # Meanwhile TypePad hit our callback, so reload the object to
                # preserve the new "verified" value.
                s = Subscription.objects.get(verify_token=verify_token)
                s.url_id = resp.subscription.url_id
                s.save()
                logging.getLogger(__name__).info("Created subscription %s." % s.url_id)
            else:
                s.delete()
                logging.getLogger(__name__).warning("Subscription failed.")
    
admin.site.register(Subscription, SubscriptionAdmin)
admin.site.register(Token)

try:
    from typepadapp.models.auth import UserForTypePadUser
except ImportError:
    pass
else:
    admin.site.register(UserForTypePadUser)
