# hack'ish support for comparing a django reversion
# history object with the current state

from diff_match_patch import diff_match_patch
import datetime

from reversion.admin import VersionAdmin
from reversion.models import Version
from django.conf.urls import url
from django.shortcuts import get_object_or_404, render
from django.contrib.admin.utils import unquote, quote
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from reversion.helpers import generate_patch_html
from django.contrib.admin import SimpleListFilter
from django.contrib.contenttypes.models import ContentType

from markitup.fields import Markup


class DateModifiedFilter(SimpleListFilter):
    title = _('Last Modified')
    parameter_name = 'moddate'

    def lookups(self, request, model_admin):
        return (
            ('today', _('Today')),
            ('yesterday', _('Since yesterday')),
            ('7 days', _('In the last 7 days')),
            ('30 days', _('In the last 30 days')),
            )

    def queryset(self, request, queryset):
        date = None
        if self.value() == 'today':
            date = datetime.date.today()
        elif self.value() == 'yesterday':
            date = datetime.date.today() - datetime.timedelta(days=1)
        elif self.value() == '7 days':
            date = datetime.date.today() - datetime.timedelta(days=7)
        elif self.value() == '30 days':
            date = datetime.date.today() - datetime.timedelta(days=30)
        if not date:
            return queryset
        content_type = ContentType.objects.get_for_model(queryset.model)
        revisions = Version.objects.filter(content_type=content_type, revision__date_created__gte=date)
        return queryset.filter(pk__in=[x.object_id for x in revisions])


class CompareVersionAdmin(VersionAdmin):

    compare_template = "admin/wafer.compare/compare.html"
    compare_list_template = "admin/wafer.compare/compare_list.html"

    # Add a compare button next to the History button.
    change_form_template = "admin/wafer.compare/change_form.html"

    def get_urls(self):
         urls = super(CompareVersionAdmin, self).get_urls()
         opts = self.model._meta
         compare_urls = [
               url("^([^/]+)/([^/]+)/compare/$", self.admin_site.admin_view(self.compare_view),
                   name='%s_%s_compare' % (opts.app_label, opts.model_name)),
               url("^([^/]+)/comparelist/$", self.admin_site.admin_view(self.comparelist_view),
                   name='%s_%s_comparelist' % (opts.app_label, opts.model_name)),
         ]
         return compare_urls + urls

    def compare_view(self, request, object_id, version_id, extra_context=None):
        """Actually compare two versions."""
        opts = self.model._meta
        object_id = unquote(object_id)
        # get_for_object's ordering means this is always the latest revision.
        current = self.revision_manager.get_for_object_reference(self.model, object_id)[0]
        # The reversion we want to compare to
        revision = self.revision_manager.get_for_object_reference(self.model, object_id).filter(id=version_id)[0]
        the_diff = []
        dmp = diff_match_patch()

        for field in (set(current.field_dict.keys()) | set(revision.field_dict.keys())):
            # These exclusions really should be configurable
            if field == 'id' or field.endswith('_rendered'):
                continue
            # KeyError's may happen if the database structure changes
            # between the creation of revisions. This isn't ideal,
            # but should not be a fatal error.
            # Log this?
            missing_field = False
            try:
                cur_val = current.field_dict[field] or ""
            except KeyError:
                cur_val = "No such field in latest version\n"
                missing_field = True
            try:
                old_val = revision.field_dict[field] or ""
            except KeyError:
                old_val = "No such field in old version\n"
                missing_field = True
            if missing_field:
                # Ensure that the complete texts are marked as changed
                # so new entires containing any of the marker words
                # don't show up as differences
                diffs = [(dmp.DIFF_DELETE, old_val), (dmp.DIFF_INSERT, cur_val)]
                patch =  dmp.diff_prettyHtml(diffs)
            elif isinstance(cur_val, Markup):
                # we roll our own diff here, so we can compare of the raw
                # markdown, rather than the rendered result.
                if cur_val.raw == old_val.raw:
                    continue
                diffs = dmp.diff_main(old_val.raw, cur_val.raw)
                patch =  dmp.diff_prettyHtml(diffs)
            elif cur_val == old_val:
                continue
            else:
                patch = generate_patch_html(revision, current, field)
            the_diff.append((field, patch))

        the_diff.sort()

        context = {
            "title": _("Comparing current %s with revision created %s") % (
                current,
                revision.revision.date_created.strftime("%Y-%m-%d %H:%m:%S")),
            "opts": opts,
            "compare_list_url": reverse("%s:%s_%s_comparelist" % (self.admin_site.name, opts.app_label, opts.model_name),
                                                                  args=(quote(object_id),)),
            "diff_list": the_diff,
        }

        extra_context = extra_context or {}
        context.update(extra_context)
        return render(request, self.compare_template or self._get_template_list("compare.html"),
                      context)

    def comparelist_view(self, request, object_id, extra_context=None):
        """Allow selecting versions to compare."""
        opts = self.model._meta
        object_id = unquote(object_id)
        current = get_object_or_404(self.model, pk=object_id)
        # As done by reversion's history_view
        action_list = [
            {
                "revision": version.revision,
                "url": reverse("%s:%s_%s_compare" % (self.admin_site.name, opts.app_label, opts.model_name), args=(quote(version.object_id), version.id)),
            } for version
              in self._order_version_queryset(self.revision_manager.get_for_object_reference(
                  self.model,
                  object_id,).select_related("revision__user"))
        ]
        context = {"action_list": action_list,
                   "opts": opts,
                   "object_id": quote(object_id),
                   "original": current,
                  }
        extra_context = extra_context or {}
        context.update(extra_context)
        return render(request, self.compare_list_template or self._get_template_list("compare_list.html"),
                      context)
