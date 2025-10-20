from django import template
from django.template.defaultfilters import stringfilter
from django.utils.safestring import mark_safe
import markdown as md

register = template.Library()


@register.filter(name="md_to_html")
@stringfilter
def md_to_html(value):
    html = md.markdown(
        value,
        extensions=[
            "fenced_code",
            "codehilite",  # syntax highlighting (requires Pygments)
            "tables",  # table support
            "toc",  # optional: table of contents
        ],
        output_format="html5",
    )
    return mark_safe(html)
