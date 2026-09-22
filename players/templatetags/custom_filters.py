from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def avatar_hue(value):
    """Cor estável por nome, para o círculo de iniciais de quem não tem foto."""
    return sum(ord(letter) for letter in str(value)) % 360
