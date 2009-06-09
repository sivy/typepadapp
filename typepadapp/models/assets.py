import re
from django.core.urlresolvers import reverse, NoReverseMatch
from django.utils.translation import ugettext as _
from urlparse import urljoin

import typepad
from django.conf import settings
from typepadapp import signals
from remoteobjects import fields
from remoteobjects.promise import ListObject
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
        try:
            return reverse('asset', args=[self.url_id])
        except NoReverseMatch:
            return None

    @property
    def type_id(self):
        if not self.object_types: return None
        return self.object_types[0].split(':')[2].lower()

    @property
    def type_label(self):
        return _(self.type_id)

    @property
    def is_comment(self):
        return self.type_id == 'comment'

    @property
    def is_local(self):
        return typepadapp.models.GROUP.id in self.groups

    def get_comments(self, start_index=1, max_results=settings.COMMENTS_PER_PAGE):
        return self.comments.filter(start_index=start_index, max_results=max_results)

    @property
    def user(self):
        return self.author

    def link_relation(self, relation):
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
        """Relative url to the comment anchor on the asset permalink page."""
        try:
            return '%s#%s' % (reverse('asset', args=[self.in_reply_to.url_id]), self.url_id)
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
        post = posts.post(self)
        # TODO - did this used to return a post asset?? (needed for ajax)
        return post


class Audio(typepad.Audio, Asset):

    @property
    def link(self):
        try:
            return self.links['enclosure'].href
        except KeyError:
            pass


class Video(typepad.Video, Asset):

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
        video = videos.post(self)
        # TODO - did this used to return a post asset?? (needed for ajax)
        return video


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
        the link, we will display a cleaned-up version of the URL itself
        (eliminating the 'http'/'https' protocol, any credentials that
        may be present, any query parameters and any trailing slash
        and obvious index page names).

        Another approach may be to attempt to retrieve the title
        of the HTML that may be returned from the link, but this would be
        an option upon creation of the asset, not upon rendering.
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
        link = links.post(self)
        # TODO - did this used to return a post asset?? (needed for ajax)
        return link


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
