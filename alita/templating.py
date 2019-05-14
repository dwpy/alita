# -*- coding: utf-8 -*-
"""
alita template.
"""
from alita.response import HtmlResponse
from jinja2 import BaseLoader, Environment as BaseEnvironment, \
     TemplateNotFound
from alita.signals import template_rendered, before_render_template


class Environment(BaseEnvironment):
    """Works like a regular Jinja2 environment but has some additional
    knowledge of how Alita's blueprint works so that it can prepend the
    name of the blueprint to referenced templates if necessary.
    """

    def __init__(self, app, **options):
        if 'loader' not in options:
            options['loader'] = app.create_global_jinja_loader()
        BaseEnvironment.__init__(self, **options)
        self.app = app


class DispatchingJinjaLoader(BaseLoader):
    """
    A loader that looks for templates in the application and all
    the blueprint folders.
    """

    def __init__(self, app):
        self.app = app

    def get_source(self, environment, template):
        for srcobj, loader in self._iter_loaders(template):
            try:
                return loader.get_source(environment, template)
            except TemplateNotFound:
                continue
        raise TemplateNotFound(template)

    def _iter_loaders(self, template):
        loader = self.app.jinja_loader
        if loader is not None:
            yield self.app, loader

        for blueprint in self.app.iter_blueprints():
            loader = blueprint.jinja_loader
            if loader is not None:
                yield blueprint, loader

    def list_templates(self):
        result = set()
        loader = self.app.jinja_loader
        if loader is not None:
            result.update(loader.list_templates())

        for blueprint in self.app.iter_blueprints():
            loader = blueprint.jinja_loader
            if loader is not None:
                for template in loader.list_templates():
                    result.add(template)

        return list(result)


async def _render(request, context, template):
    """Renders the template and fires the signal"""
    await request.update_template_context(context)
    before_render_template.send(request.app, template=template, context=context)
    rv = await template.render_async(context)
    template_rendered.send(request.app, template=template, context=context)
    return rv


async def render_template(request, template_name_or_list, **context):
    """
    Renders a template from the template folder with the given
    context.

    :param request: app request object.
    :param template_name_or_list: the name of the template to be
                                  rendered, or an iterable with template names
                                  the first one existing will be rendered
    :param context: the variables that should be available in the
                    context of the template.
    """
    return HtmlResponse(await _render(
        request, context,
        request.app.jinja_env.get_or_select_template(template_name_or_list)))


async def render_template_string(request, source, **context):
    """
    Renders a template from the given template source string
    with the given context. Template variables will be autoescaped.

    :param request: app request object.
    :param source: the source code of the template to be
                   rendered
    :param context: the variables that should be available in the
                    context of the template.
    """
    return HtmlResponse(await _render(
        request, context, request.app.jinja_env.from_string(source)))
