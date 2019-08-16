import gzip
import io
import json

from django.http import HttpRequest
from django.http import HttpResponseForbidden
from django.http import HttpResponseNotFound
from django.contrib.sessions.backends.db import SessionStore
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def decode_data(data, compression=0):
    if compression:
        with gzip.GzipFile(mode="rb", fileobj=io.BytesIO(data)) as gz:
            data = gz.read()

    try:
        data = json.loads(data.decode())
    except (ValueError, UnicodeDecodeError):
        data = {'data': data }

    return data

@csrf_exempt
class DankiMiddleware:
    def __init__(self):
        self.session_manager = SessionStore()

    def process_request(self, request: HttpRequest):
        if request.method != 'POST': return HttpResponseNotFound()

        # Check for valid session keys, hkey and then skey
        hkey = None if 'k' not in request.POST else request.POST['k']
        if 'danki_k' not in request.session or hkey != request.session['danki_k']:
            skey = None if 'sk' not in request.POST else request.POST['sk']
            if 'danki_sk' not in request.session or skey != request.session['danki_sk']:
                if not request.path.endswith('sync/hostKey'):
                    return HttpResponseForbidden()

        compression = 0 if 'c' not in request.POST else request.POST['c']
        request.danki_data = {} if 'data' not in request.FILES else decode_data(request.FILES['data'].file.read(), compression)