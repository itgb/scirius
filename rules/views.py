"""
Copyright(C) 2014, Stamus Networks
Written by Eric Leblond <eleblond@stamus-networks.com>

This file is part of Scirius.

Scirius is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Scirius is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Scirius.  If not, see <http://www.gnu.org/licenses/>.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.db import IntegrityError

from scirius.utils import scirius_render, scirius_listing

from rules.models import Ruleset, Source, Category, Rule

import json
import re

from datetime import datetime
from time import time
import django_tables2 as tables
from tables import *
from forms import *

# Create your views here.
def index(request):
    ruleset_list = Ruleset.objects.all().order_by('-created_date')[:5]
    source_list = Source.objects.all().order_by('-created_date')[:5]
    context = {'ruleset_list': ruleset_list,
                'source_list': source_list}
    try:
        from suricata.models import Suricata
        suricata = Suricata.objects.all()
        if suricata != None:
            context['suricata'] = suricata[0]
    except:
        pass
    return scirius_render(request, 'rules/index.html', context)

def sources(request):
    return scirius_listing(request, Source, 'Sources')

def source(request, source_id, error=None):
    source = get_object_or_404(Source, pk=source_id)
    cats = CategoryTable(Category.objects.filter(source = source))
    tables.RequestConfig(request).configure(cats)
    context = {'source': source, 'categories': cats}
    if error:
        context['error'] = error
    return scirius_render(request, 'rules/source.html', context)

def categories(request):
    return scirius_listing(request, Category, 'Categories')

def category(request, cat_id):
    cat = get_object_or_404(Category, pk=cat_id)
    rules = RuleTable(Rule.objects.filter(category = cat))
    tables.RequestConfig(request).configure(rules)
    category_path = [ cat.source ]
    context = {'category': cat, 'rules': rules, 'object_path': category_path}
    return scirius_render(request, 'rules/category.html', context)

class Reference:
    def __init__(self, key, value):
        self.value = value
        self.key = key
        self.url = None

def rule(request, rule_id, key = 'pk'):
    if request.is_ajax():
        rule = get_object_or_404(Rule, sid=rule_id)
        data = { 'msg': rule.msg, 'sid': rule.sid, 'content': rule.content}
        return HttpResponse(json.dumps(data),
                            content_type="application/json")
    if key == 'pk':
        rule = get_object_or_404(Rule, pk=rule_id)
    else:
        rule = get_object_or_404(Rule, sid=rule_id)
    rule_path = [rule.category.source, rule.category]

    references = []
    for ref in re.findall("reference:(\w+),(\S+);", rule.content):
        refer = Reference(ref[0], ref[1])
        if refer.key == 'url':
            refer.url = "http://" + refer.value
        elif refer.key == 'cve':
            refer.url = "http://web.nvd.nist.gov/view/vuln/detail?vulnId=CVE-" + refer.value
            refer.key = refer.key.upper()
        elif refer.key == 'bugtraq':
            refer.url = "http://www.securityfocus.com/bid/" + refer.value
        references.append(refer)
    context = {'rule': rule, 'references': references, 'object_path': rule_path}
    return scirius_render(request, 'rules/rule.html', context)


def suppress_rule(request, rule_id):
    rule_object = get_object_or_404(Rule, sid=rule_id)
    if request.method == 'POST': # If the form has been submitted...
        form = RuleSuppressForm(request.POST)
        if form.is_valid(): # All validation rules pass
            ruleset = form.cleaned_data['ruleset']
            ruleset.suppressed_rules.add(rule_object)
            ruleset.save()
        return redirect(rule_object)
    form = RuleSuppressForm()
    context = { 'rule': rule_object, 'form': form }
    return scirius_render(request, 'rules/suppress_rule.html', context)

def update_source(request, source_id):
    src = get_object_or_404(Source, pk=source_id)
    try:
        src.update()
    except IOError, errors:
        return source(request, source_id, error="Can not fetch data: %s" % (errors))
    return redirect(src)

def diff_source(request, source_id):
    source = get_object_or_404(Source, pk=source_id)
    diff = source.diff()
    return scirius_render(request, 'rules/source.html', { 'source': source, 'diff': diff })

def add_source(request):
    if request.method == 'POST': # If the form has been submitted...
        form = SourceForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            try:
                source = Source.objects.create(name = form.cleaned_data['name'],
                        uri = form.cleaned_data['uri'],
                        method = form.cleaned_data['method'],
                        created_date = datetime.now(),
                        datatype = form.cleaned_data['datatype'],
                        )
            except IntegrityError, error:
                return scirius_render(request, 'rules/add_source.html', { 'form': form, 'error': error })
            return redirect(source)
    else:
        form = SourceForm() # An unbound form

    return scirius_render(request, 'rules/add_source.html', { 'form': form, })

def edit_source(request, source_id):
    source = get_object_or_404(Source, pk=source_id)

    if request.method == 'POST': # If the form has been submitted...
        form = SourceForm(request.POST, instance=source)
        try:
            form.save()
            return redirect(source)
        except ValueError:
            pass
    else:
        form = SourceForm(instance = source)

    return scirius_render(request, 'rules/add_source.html', { 'form': form, 'source': source})

def rulesets(request):
    return scirius_listing(request, Ruleset, 'Rulesets')

def ruleset(request, ruleset_id, mode = 'struct'):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    if mode == 'struct':
        categories_list = {}
        sources = ruleset.sources.all()
        for sourceatversion in sources:
            cats = CategoryTable(ruleset.categories.filter(source = sourceatversion.source))
            tables.RequestConfig(request).configure(cats)
            categories_list[sourceatversion.source.name] = cats
        rules = RuleTable(ruleset.suppressed_rules.all())
        tables.RequestConfig(request).configure(rules)
        context = {'ruleset': ruleset, 'categories_list': categories_list, 'sources': sources, 'rules': rules, 'mode': mode}
    elif mode == 'display':
        rules = RuleTable(ruleset.generate())
        tables.RequestConfig(request).configure(rules)
        context = {'ruleset': ruleset, 'rules': rules, 'mode': mode}
    elif mode == 'export':
        rules = ruleset.generate()
        file_content = "# Rules file for " + ruleset.name + " generated by Scirius at " + str(datetime.now()) + "\n"
        for rule in rules:
            file_content += rule.content
        response = HttpResponse(file_content, content_type="text/plain")
        response['Content-Disposition'] = 'attachment; filename=scirius.rules'
        return response
    return scirius_render(request, 'rules/ruleset.html', context)

def add_ruleset(request):
    if request.method == 'POST': # If the form has been submitted...
        form = RulesetForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            # Process the data in form.cleaned_data
            # ...
            try:
                ruleset = form.create_ruleset()
            except IntegrityError, error:
                return scirius_render(request, 'rules/add_ruleset.html', { 'form': form, 'error': error })
            return redirect(ruleset)
    else:
        form = RulesetForm() # An unbound form

    return scirius_render(request, 'rules/add_ruleset.html', { 'form': form, })

def update_ruleset(request, ruleset_id):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    ruleset.update()
    return redirect(ruleset)

def edit_ruleset(request, ruleset_id):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    if request.method == 'POST': # If the form has been submitted...
        # check if this is a categories edit
        # ID is unique so we can just look by indice and add
        if request.POST.has_key('source'):
            sourceat = get_object_or_404(SourceAtVersion, pk=request.POST['source'])
            # clean ruleset
            ruleset.categories.clear()
            # add updated entries
            for cat in request.POST.getlist('category_selection'):
                category = get_object_or_404(Category, pk=cat)
                ruleset.categories.add(category)
            ruleset.save()
        elif request.POST.has_key('rules'):
            for rule in request.POST.getlist('rule_selection'):
                rule_object = get_object_or_404(Rule, pk=rule)
                ruleset.suppressed_rules.remove(rule_object)
            ruleset.save()

        return redirect(ruleset)
    else:
        cats_selection = []
        categories_list = {}
        sources = ruleset.sources.all()
        ruleset_cats = ruleset.categories.all()
        for sourceatversion in sources:
            src_cats = Category.objects.filter(source = sourceatversion.source)
            for pcats in src_cats:
                if pcats in ruleset_cats:
                    cats_selection.append(str(pcats.id))
            cats = EditCategoryTable(src_cats)
            tables.RequestConfig(request,paginate = False).configure(cats)
            categories_list[sourceatversion.source.name] = cats
        rules = EditRuleTable(ruleset.suppressed_rules.all())
        tables.RequestConfig(request, paginate = False).configure(rules)
        context = {'ruleset': ruleset, 'categories_list': categories_list, 'sources': sources, 'rules': rules, 'cats_selection': ", ".join(cats_selection) }
        if request.GET.has_key('mode'):
                context['mode'] = request.GET['mode']
        return scirius_render(request, 'rules/edit_ruleset.html', context)

def ruleset_add_supprule(request, ruleset_id):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    if request.method == 'POST': # If the form has been submitted...
        if request.POST.has_key('search'):
            #FIXME Protection on SQL injection ?
            rules = EditRuleTable(Rule.objects.filter(content__icontains=request.POST['search']))
            tables.RequestConfig(request).configure(rules)
            context = { 'ruleset': ruleset, 'rules': rules }
            return scirius_render(request, 'rules/search_rule.html', context)
        elif request.POST.has_key('rule_selection'):
            for rule in request.POST.getlist('rule_selection'):
                rule_object = get_object_or_404(Rule, pk=rule)
                ruleset.suppressed_rules.add(rule_object)
            ruleset.save()
        return redirect(ruleset)
    context = { 'ruleset': ruleset }
    return scirius_render(request, 'rules/search_rule.html', context)

def delete_ruleset(request, ruleset_id):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    if request.method == 'POST': # If the form has been submitted...
        ruleset.delete()
        return redirect("/rules/ruleset/")
    else:
        context = {'object': ruleset, 'delfn': 'delete_ruleset' }
        return scirius_render(request, 'rules/delete.html', context)

def copy_ruleset(request, ruleset_id):
    ruleset = get_object_or_404(Ruleset, pk=ruleset_id)
    if request.method == 'POST': # If the form has been submitted...
        form = RulesetCopyForm(request.POST) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            copy = ruleset.copy(form.cleaned_data['name'])
            return redirect(copy)
    else:
        form = RulesetCopyForm()
    context = {'object': ruleset , 'form': form}
    return scirius_render(request, 'rules/copy_ruleset.html', context)
