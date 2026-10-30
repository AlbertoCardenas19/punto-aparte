from django import template

from config.formatos import formatear_clp


register = template.Library()
register.filter("clp", formatear_clp)
