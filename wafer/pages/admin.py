from django.contrib import admin

from wafer.pages.models import File, Page

from wafer.compare.admin import CompareVersionAdmin, DateModifiedFilter


class PageAdmin(CompareVersionAdmin, admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}
    list_display = ('name', 'slug', 'get_people_display_names', 'get_in_schedule')

    list_filter = (DateModifiedFilter,)



admin.site.register(Page, PageAdmin)
admin.site.register(File)
