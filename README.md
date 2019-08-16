## Sanki
As in (Anki) (S)erver.

This is basically [tsudoku][1]'s `anki-sync-server` but I put it into the Django framework
so that I could easily add some RESTful endpoints.

Layout:
* `sanki`: This is the Django Project
* `ranki`: This is the Django App for the Rest API, as in (Anki) + (r)est
* `danki`: This is a Django'd up version of [tsudoku]([1])'s `ankisynd`, as in (Anki) + ankisync(d)
* `wanki`: This is the Django App for the web interface (creating users). (Anki) + (w)eb

[1]: https://github.com/tsudoko/anki-sync-server