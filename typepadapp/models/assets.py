import re
from urlparse import urljoin

from django.core.urlresolvers import reverse, NoReverseMatch
from django.utils.translation import ugettext as _
from django.conf import settings

import typepad
from typepadapp import signals
from remoteobjects import fields
from remoteobjects.promise import ListObject
from remoteobjects.http import HttpObject
import typepadapp.models


class ListObjectSignalDispatcher(object):
    """
    Override the post method of ListObject so we can signal when
    an asset is created.

    """
    def post(self, obj, *args, **kwargs):
        super(ListObjectSignalDispatcher, self).post(obj, *args, **kwargs)
        signals.post_save.send(sender=self.__class__, instance=obj)
ListObject.__bases__ = (ListObjectSignalDispatcher,) + ListObject.__bases__


# Additional methods for all asset models:
class Asset(typepad.Asset):

    def __unicode__(self):
        return self.title or self.content

    def __str__(self):
        return self.__unicode__()

    def get_absolute_url(self):
        """Relative url to the asset permalink page."""
        if self.is_local:
            try:
                return reverse('asset', args=[self.url_id])
            except NoReverseMatch:
                pass

        try:
            return self.links['alternate'].href
        except KeyError:
            return None
    
    @property
    def feed_url(self):
        """URL for atom feed of entry comments."""
        try:
            url = self.get_absolute_url()[1:] # remove starting /
            return reverse('feeds', kwargs={'url': url})
        except NoReverseMatch:
            return None

    @property
    def type_id(self):
        object_type = self.primary_object_type()
        if object_type is None: return None
        return object_type.split(':')[2].lower()

    @property
    def type_label(self):
        """ Provides a localized string identifying the type of asset. """
        return _(self.type_id)

    @property
    def is_comment(self):
        """ Boolean property identifying whether the asset is a comment or not. """
        return self.type_id == 'comment'

    @property
    def is_local(self):
        """ Boolean property identifying whether the asset belongs to the
        group assigned to typepadapp.models.GROUP. """
        return typepadapp.models.GROUP.id in self.groups

    def get_comments(self, start_index=1, max_results=settings.COMMENTS_PER_PAGE):
        return self.comments.filter(start_index=start_index, max_results=max_results)

    @property
    def user(self):
        """ An alias for the author property. """
        return self.author

    def link_relation(self, relation):
        """ A method that yields a Link object of the specified relation
        from the asset's 'links' member.

        If the relation does not exist, one is added and the empty Link
        object is returned to be populated. """
        try:
            links = self.__dict__['links']
        except KeyError:
            links = typepad.LinkSet()
            self.links = links

        try:
            return links[relation]
        except KeyError:
            l = typepad.Link()
            l.rel = relation
            links.add(l)
            return l


class Comment(typepad.Comment, Asset):

    def get_absolute_url(self):
        """Relative URL to the comment anchor on the asset permalink page."""
        try:
            return '%s#comment-%s' % (reverse('asset', args=[self.in_reply_to.url_id]), self.url_id)
        except NoReverseMatch:
            return None


class Favorite(typepad.Favorite, Asset):
    pass


class Post(typepad.Post, Asset):

    def save(self, group=None):
        # Warning - this only handles create, not update
        # so don't call this more than once
        assert group, "group parameter is unassigned"
        posts = group.post_assets
        posts.post(self)


class Audio(typepad.Audio, Asset):

    @property
    def link(self):
        try:
            return self.links['enclosure'].href
        except KeyError:
            pass


class Video(typepad.Video, Asset):

    class ConduitError:
        def __init__(self, message):
            self.message = message

    def get_html(self):
        return self.link_relation('enclosure').html

    def set_html(self, value):
        self.link_relation('enclosure').html = value

    html = property(get_html, set_html)

    def get_link(self):
        return self.link_relation('enclosure').href

    def set_link(self, value):
        self.link_relation('enclosure').href = value

    link = property(get_link, set_link)

    def save(self, group=None):
        # Warning - this only handles create, not update
        # so don't call this more than once
        assert group, "group parameter is unassigned"
        videos = group.video_assets
        try:
            videos.post(self)
        except HttpObject.ServerError, ex:
            # Bad video?
            try:
                reason = ex.response_error
            except AttributeError: # no reason from the API?
                reason = _('You have entered a URL that is either invalid or a URL for a video that can no longer be found.')
            raise self.ConduitError(reason)


class Photo(typepad.Photo, Asset):

    @property
    def link(self):
        if not self.links or not self.links['rel__enclosure']:
            return None
        best = self.links['rel__enclosure'].link_by_width()
        if not best: return None
        return best.href


class LinkAsset(typepad.LinkAsset, Asset):

    @property
    def link_title(self):
        """ Returns a title suitable for displaying the link asset title.

        This handles the case where a link asset has a link (which is
        a required field) but no title. If no actual title exists for
        the link, a cleaned-up version of the URL itself (eliminating the
        'http'/'https' protocol, any credentials that may be present, any
        query parameters and any trailing slash and obvious index page names).

        Another approach may be to attempt to retrieve the title of the HTML
        that may be returned from the link, but this would be an option upon
        creation of the asset, not upon rendering.
        """
        try:
            title = self.title
            assert title is not None and title != ''
            return title
        except:
            pass

        # use link as the display'd value; needs a shave and a haircut tho
        link = self.link
        link = re.sub('^https?://(?:.+?@)?', '', link)
        link = re.sub('^www\.', '', link)
        link = re.sub('\?.+$', '', link)
        link = re.sub('/(?:default|index)(\.\w+)?$', '', link)
        link = re.sub('/$', '', link)
        return link

    def get_link(self):
        return self.link_relation('target').href

    def set_link(self, value):
        self.link_relation('target').href = value

    link = property(get_link, set_link)

    def save(self, group=None):
        # Warning - this only handles create, not update
        # so don't call this more than once
        assert group, "group parameter is unassigned"
        links = group.link_assets
        links.post(self)


class Event(typepad.Event):

    @property
    def verb(self):
        try:
            return self.verbs[0]
        except IndexError:
            # No verbs
            return None

    @property
    def is_new_asset(self):
        return self.verb == 'tag:api.typepad.com,2009:NewAsset'

    @property
    def is_added_favorite(self):
        return self.verb == 'tag:api.typepad.com,2009:AddedFavorite'

    @property
    def is_local_asset(self):
        return self.object and isinstance(self.object, Asset) \
            and self.object.is_local
