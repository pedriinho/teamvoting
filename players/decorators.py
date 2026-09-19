from functools import wraps

from django.http import HttpResponseForbidden

from .utils import are_teams_available, is_voting_open


def teams_released_only(view_func):
    """Libera o acesso somente fora da janela de votação configurada."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        html = """
            <!DOCTYPE html>
            <html lang="pt-br">
            <head>
                <meta charset="UTF-8">
                <title>Acesso Negado</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-100 flex items-center justify-center h-screen">
                <div class="bg-white p-8 rounded-xl shadow-lg max-w-md text-center">
                    <i class="fas fa-exclamation-triangle text-yellow-500 text-4xl mb-4"></i>
                    <h1 class="text-2xl font-bold text-gray-800 mb-2">Acesso Negado</h1>
                    <p class="text-gray-600">Os times ainda não foram liberados. Eles ficam disponíveis assim que a votação se encerra.</p>
                    <a href="/" class="mt-4 inline-block bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded transition">Voltar para Home</a>
                </div>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/js/all.min.js"></script>
            </body>
            </html>
        """
        if are_teams_available():
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden(html)
    return _wrapped_view


def vote_open_only(view_func):
    """Libera o acesso somente durante a janela de votação configurada."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        html = """
            <!DOCTYPE html>
            <html lang="pt-br">
            <head>
                <meta charset="UTF-8">
                <title>Votação Encerrada</title>
                <script src="https://cdn.tailwindcss.com"></script>
            </head>
            <body class="bg-gray-100 flex items-center justify-center h-screen">
                <div class="bg-white p-8 rounded-xl shadow-lg max-w-md text-center">
                    <i class="fas fa-ban text-red-500 text-4xl mb-4"></i>
                    <h1 class="text-2xl font-bold text-gray-800 mb-2">Votação Encerrada</h1>
                    <p class="text-gray-600">A votação só fica disponível dentro do horário configurado pelo administrador.</p>
                    <a href="/" class="mt-4 inline-block bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded transition">Voltar para Home</a>
                </div>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/js/all.min.js"></script>
            </body>
            </html>
        """
        if is_voting_open():
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden(html)
    return _wrapped_view
