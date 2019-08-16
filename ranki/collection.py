from django.http import JsonResponse
from django.views import View


class CollectionView(View):
    def get(self, *args, **kwargs):
        return JsonResponse({
            "message": "Hello!"
        })
