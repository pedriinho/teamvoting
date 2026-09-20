from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

SIZE = 256
MAX_BYTES = 5 * 1024 * 1024


class InvalidAvatarError(Exception):
    pass


def process(upload):
    """Recorta no centro, reduz para um quadrado de 256px e devolve um JPEG."""
    if upload.size > MAX_BYTES:
        raise InvalidAvatarError('A imagem precisa ter no máximo 5 MB.')

    try:
        image = Image.open(upload)
        image = ImageOps.exif_transpose(image)
        image = image.convert('RGB')
        image = ImageOps.fit(image, (SIZE, SIZE), method=Image.LANCZOS)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise InvalidAvatarError('Não foi possível ler a imagem enviada.') from error

    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=85, optimize=True)

    return ContentFile(buffer.getvalue())
