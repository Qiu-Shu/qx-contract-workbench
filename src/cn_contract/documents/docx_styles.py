"""Bounded dependency inspection, not a Word rendering or full style engine.

Positive visibility flags anywhere in the effective style chain remain manual.
Conflicting toggle/override combinations are deliberately not declared visible.
"""
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


class StyleDependencyError(ValueError):
    pass


class EffectiveStyles:
    def __init__(self, root=None, *, unavailable=False, fallback=None):
        self.root = root
        self.unavailable = unavailable
        self.styles = {}
        self.defaults = {}
        self.invalid = False
        self.fallback = fallback
        if root is not None:
            if len(root.findall(f'{{{W}}}docDefaults')) > 1:
                self.invalid = True
            for defaults in root.findall(f'{{{W}}}docDefaults'):
                for kind in ('pPr', 'rPr'):
                    nodes = defaults.findall(f'{{{W}}}{kind}Default')
                    if len(nodes) > 1 or any(len(node.findall(f'{{{W}}}{kind}')) > 1 for node in nodes):
                        self.invalid = True
            for node in root.findall(f'{{{W}}}style'):
                identifier = node.get(f'{{{W}}}styleId')
                kind = node.get(f'{{{W}}}type')
                if not identifier or identifier in self.styles:
                    self.invalid = True
                self.styles[identifier] = node
                if node.get(f'{{{W}}}default') not in {None, '0', 'false', 'off', '1', 'true', 'on'}:
                    self.invalid = True
                if node.get(f'{{{W}}}default') in {'1', 'true', 'on'}:
                    if kind in self.defaults:
                        self.invalid = True
                    self.defaults[kind] = identifier

    def chain(self, identifier, kind):
        if self.unavailable or self.invalid:
            raise StyleDependencyError('untrusted_styles')
        if not identifier:
            return []
        result, seen = [], set()
        while identifier:
            if identifier in seen or len(seen) >= 64:
                raise StyleDependencyError('cycle_or_depth')
            seen.add(identifier)
            node = self.styles.get(identifier)
            if node is None and self.fallback is not None:
                node = self.fallback.styles.get(identifier)
            if node is None or node.get(f'{{{W}}}type') != kind:
                raise StyleDependencyError('missing_or_wrong_type')
            if any(len(node.findall(f'{{{W}}}{prop}')) > 1 for prop in ('pPr', 'rPr', 'tblPr')):
                raise StyleDependencyError('ambiguous_style_properties')
            result.append(node)
            bases = node.findall(f'{{{W}}}basedOn')
            if len(bases) > 1:
                raise StyleDependencyError('ambiguous_base')
            identifier = bases[0].get(f'{{{W}}}val') if bases else None
            if bases and not identifier:
                raise StyleDependencyError('missing_base')
        return list(reversed(result))

    def paragraph_chain(self, paragraph):
        if len(paragraph.findall(f'{{{W}}}pPr')) > 1:
            raise StyleDependencyError('ambiguous_paragraph_properties')
        styles = paragraph.findall(f'{{{W}}}pPr/{{{W}}}pStyle')
        if len(styles) > 1:
            raise StyleDependencyError('ambiguous_paragraph_style')
        identifier = styles[0].get(f'{{{W}}}val') if styles else self.defaults.get('paragraph')
        if styles and not identifier:
            raise StyleDependencyError('missing_paragraph_style')
        return self.chain(identifier, 'paragraph')

    @staticmethod
    def hidden(properties):
        for prop in properties:
            if prop is None:
                continue
            for name in ('vanish', 'webHidden'):
                flags = prop.iter(f'{{{W}}}{name}')
                for flag in flags:
                    value = flag.get(f'{{{W}}}val', 'true')
                    if value not in {'0', 'false', 'off', '1', 'true', 'on'}:
                        raise StyleDependencyError('invalid_visibility')
                    if value in {'1', 'true', 'on'}:
                        return True
        return False

    def run_properties(self, paragraph, run):
        if len(run.findall(f'{{{W}}}rPr')) > 1:
            raise StyleDependencyError('ambiguous_run_properties')
        chain = self.paragraph_chain(paragraph)
        styles = run.findall(f'{{{W}}}rPr/{{{W}}}rStyle')
        if len(styles) > 1:
            raise StyleDependencyError('ambiguous_run_style')
        identifier = styles[0].get(f'{{{W}}}val') if styles else self.defaults.get('character')
        if styles and not identifier:
            raise StyleDependencyError('missing_run_style')
        chain += self.chain(identifier, 'character')
        properties = []
        if self.root is not None:
            properties.append(self.root.find(f'{{{W}}}docDefaults/{{{W}}}rPrDefault/{{{W}}}rPr'))
        properties.extend(node for node in chain)
        properties.append(run.find(f'{{{W}}}rPr'))
        return properties

    def run_hidden(self, paragraph, run):
        return self.hidden(self.run_properties(paragraph, run))

    def color_uncertain(self, paragraph, run, backgrounds=()):
        """Finite color subset; unresolved themes/patterns require source checking.

        This is a conservative extraction gate, not a Word renderer. A 4.5
        contrast cutoff routes low-contrast text to independent lawyer records.
        """
        foreground, background = '000000', 'FFFFFF'
        properties = [node.find(f'{{{W}}}rPr') if node is not None and node.tag == f'{{{W}}}style' else node
                      for node in self.run_properties(paragraph, run)]
        paragraph_props = [node.find(f'{{{W}}}pPr') for node in self.paragraph_chain(paragraph)]
        paragraph_props.append(paragraph.find(f'{{{W}}}pPr'))
        for prop in (*backgrounds, *paragraph_props, *properties):
            if prop is None:
                continue
            for node in prop.iter():
                name = node.tag.removeprefix(f'{{{W}}}')
                if name not in ('color', 'shd', 'highlight', 'background'):
                    continue
                if any('theme' in key.lower() for key in node.attrib):
                    return True
                if name == 'highlight':
                    if node.get(f'{{{W}}}val') != 'none': return True
                    continue
                if name == 'shd' and node.get(f'{{{W}}}val', 'clear') not in ('clear', 'nil'):
                    return True
                key = 'val' if name == 'color' else ('color' if name == 'background' else 'fill')
                value = node.get(f'{{{W}}}{key}', 'auto')
                if value == 'auto':
                    # Automatic color depends on the rendering environment.
                    if name == 'color': foreground = '000000'
                    else: return True
                elif len(value) != 6 or any(c not in '0123456789abcdefABCDEF' for c in value):
                    return True
                elif name == 'color': foreground = value
                else: background = value
        def luminance(value):
            channels = [int(value[i:i+2], 16) / 255 for i in (0, 2, 4)]
            linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
            return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
        light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (light + .05) / (dark + .05) < 4.5

    def table_chain(self, table):
        if len(table.findall(f'{{{W}}}tblPr')) > 1:
            raise StyleDependencyError('ambiguous_table_properties')
        references = table.findall(f'{{{W}}}tblPr/{{{W}}}tblStyle')
        if len(references) > 1:
            raise StyleDependencyError('ambiguous_table_style')
        identifier = references[0].get(f'{{{W}}}val') if references else self.defaults.get('table')
        if references and not identifier:
            raise StyleDependencyError('missing_table_style')
        return self.chain(identifier, 'table')

    def table_hidden(self, table):
        # Conditional table style regions are not rendered; any visibility flag
        # in the referenced chain conservatively makes the table manual.
        return self.hidden(self.table_chain(table))

    def numbering_used(self, paragraph, numbering_roots):
        chain = self.paragraph_chain(paragraph)
        properties = []
        if self.root is not None:
            properties.append(self.root.find(f'{{{W}}}docDefaults/{{{W}}}pPrDefault/{{{W}}}pPr'))
        properties.extend(node.find(f'{{{W}}}pPr') for node in chain)
        properties.append(paragraph.find(f'{{{W}}}pPr'))
        number = None
        for prop in properties:
            if prop is None:
                continue
            numprs = prop.findall(f'{{{W}}}numPr')
            if len(numprs) > 1:
                raise StyleDependencyError('ambiguous_numbering')
            if numprs:
                ids = numprs[0].findall(f'{{{W}}}numId')
                if len(ids) > 1:
                    raise StyleDependencyError('ambiguous_numbering_id')
                if ids:
                    value = ids[0].get(f'{{{W}}}val', '')
                    if not value.isascii() or not value.isdecimal() or len(value) > 10:
                        raise StyleDependencyError('invalid_numbering_id')
                    number = int(value)
                elif number is None:
                    # A level without a resolvable list is a semantic gap too.
                    return True
        if number is not None:
            return number != 0
        identifiers = {node.get(f'{{{W}}}styleId') for node in chain}
        return any(node.get(f'{{{W}}}val') in identifiers
                   for root in numbering_roots for node in root.iter(f'{{{W}}}pStyle'))
