"""Release isolation checks; these tests never connect to a server."""
import unittest
from install import BEGIN, END, LOCATIONS, OLD_SERVICES, ROOT, SERVICE, allowed, nginx_candidate

BASE = '''server {
    listen 80;
    server_name 8.141.114.201;
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl;
    server_name 8.141.114.201;
    # BEGIN GOTC HACKATHON MANAGED LOCATION
    location = /gotc { return 308 /gotc/; }
    location ^~ /gotc/ { proxy_pass http://127.0.0.1:5274; }
    # END GOTC HACKATHON MANAGED LOCATION
    location ^~ /hackathon/ { proxy_pass http://127.0.0.1:5273; }
    location / { proxy_pass http://127.0.0.1:8000; }
}
'''


class ReleaseIsolationTest(unittest.TestCase):
    def test_new_route_preserves_every_existing_route(self):
        candidate = nginx_candidate(BASE)
        self.assertEqual(candidate.replace("\n" + LOCATIONS, ""), BASE)
        self.assertEqual(candidate.count(BEGIN), 1)
        self.assertEqual(candidate.count(END), 1)
        self.assertIn("location ^~ /chuyi/", candidate)
        self.assertIn("127.0.0.1:5275", candidate)
        self.assertEqual(nginx_candidate(candidate), candidate)

    def test_only_chuyi_managed_block_can_be_replaced(self):
        old = BASE.replace("    location / { proxy_pass http://127.0.0.1:8000; }", BEGIN + "    location ^~ /chuyi/ { return 503; }\n" + END + "    location / { proxy_pass http://127.0.0.1:8000; }")
        candidate = nginx_candidate(old)
        self.assertNotIn("return 503", candidate)
        self.assertIn("location ^~ /gotc/ { proxy_pass http://127.0.0.1:5274; }", candidate)
        self.assertEqual(candidate.count(BEGIN), 1)

    def test_foreign_chuyi_route_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Unmanaged CHUYI"):
            nginx_candidate(BASE.replace("    location / { proxy_pass", "    location /chuyi/ { return 404; }\n    location / { proxy_pass"))

    def test_ambiguous_https_server_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            nginx_candidate(BASE + BASE)

    def test_private_material_cannot_enter_release(self):
        for name in [".runtime/admin-access.txt", "server/data/event.sqlite3", "server/test_api.py", "server/secret.py", "assets/credential.png", "../index.html", "deploy/install.py"]:
            with self.subTest(name=name):
                self.assertFalse(allowed(name))
        for name in ["index.html", "platform.js", "server/app.py", "assets/hero.webp", "downloads/chuyi-hackathon.ics"]:
            with self.subTest(name=name):
                self.assertTrue(allowed(name))

    def test_service_and_existing_gotc_stay_separate(self):
        self.assertEqual(str(ROOT).replace("\\", "/"), "/opt/chuyi-hackathon")
        self.assertIn("gotc-hackathon", OLD_SERVICES)
        self.assertNotIn("chuyi-hackathon", OLD_SERVICES)
        self.assertIn("Environment=CHUYI_PORT=5275", SERVICE)
        self.assertIn("Environment=CHUYI_BASE_PATH=/chuyi", SERVICE)
        self.assertNotIn("GOTC_", SERVICE)
        self.assertIn("ProtectSystem=strict", SERVICE)
        self.assertIn("ReadWritePaths=/opt/chuyi-hackathon/data", SERVICE)


if __name__ == "__main__":
    unittest.main()
