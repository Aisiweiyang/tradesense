"""用户管理：owner 专属 CRUD、自我保护、末位 owner 保护和组织隔离。"""
from tests.conftest import auth_headers


def test_owner_lists_and_creates_users(client):
    h = auth_headers(client)
    me = client.get("/api/auth/me", headers=h).json()

    r = client.get("/api/users", headers=h)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(u["id"] == me["id"] for u in items)
    assert r.json()["owner_count"] >= 1

    r = client.post("/api/users", headers=h, json={
        "email": "newmate@test.cn", "name": "新同事", "password": "start12345",
        "role": "member"})
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "member"

    # 新同事能登录
    assert client.post("/api/auth/login", json={
        "email": "newmate@test.cn", "password": "start12345"}).status_code == 200


def test_create_user_validations(client):
    h = auth_headers(client)
    r = client.post("/api/users", headers=h, json={
        "email": "dup@test.cn", "name": "x", "password": "start12345", "role": "boss"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_role"

    r = client.post("/api/users", headers=h, json={
        "email": "owner@test.cn", "name": "dup", "password": "start12345", "role": "member"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_member_cannot_manage_users(client, db):
    from app.models import User
    from app.security import hash_password
    db.add(User(org_id=1, email="um@test.cn", name="m",
                password_hash=hash_password("password123"), role="member"))
    db.commit()
    member = auth_headers(client, "um@test.cn")
    assert client.get("/api/users", headers=member).status_code == 403
    assert client.post("/api/users", headers=member, json={
        "email": "x@x.cn", "name": "x", "password": "start12345"}).status_code == 403


def test_patch_role_self_demote_and_last_owner_guard(client):
    h = auth_headers(client)
    me = client.get("/api/auth/me", headers=h).json()
    # 自己不能改自己的角色
    r = client.patch(f"/api/users/{me['id']}", headers=h, json={"role": "member"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_demote"

    # 正确的降级流程：先建第二个 owner，用新 owner 登录来降级旧 owner
    client.post("/api/users", headers=h, json={
        "email": "owner2u@test.cn", "name": "二当家", "password": "start12345",
        "role": "owner"})
    second = auth_headers(client, "owner2u@test.cn", "start12345")
    assert client.patch(f"/api/users/{me['id']}", headers=second,
                        json={"role": "member"}).status_code == 200
    # 旧 owner 权限随即丢失
    assert client.get("/api/users", headers=h).status_code == 403
    # 新 owner 不能改自己的角色（自我保护对所有 owner 一致）
    me2 = client.get("/api/auth/me", headers=second).json()
    assert client.patch(f"/api/users/{me2['id']}", headers=second,
                        json={"role": "member"}).status_code == 409


def test_deactivate_guards_and_login_cut(client):
    h = auth_headers(client)
    me = client.get("/api/auth/me", headers=h).json()
    # 不能停用自己
    r = client.patch(f"/api/users/{me['id']}", headers=h, json={"is_active": False})
    assert r.status_code == 409 and r.json()["error"]["code"] == "self_deactivate"

    # 建一个 member → 停用 → 登录被拒 → 重置密码并启用
    u = client.post("/api/users", headers=h, json={
        "email": "cycle@test.cn", "name": "起停", "password": "start12345",
        "role": "member"}).json()
    assert client.patch(f"/api/users/{u['id']}", headers=h,
                        json={"is_active": False}).status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "cycle@test.cn", "password": "start12345"}).status_code == 403
    client.patch(f"/api/users/{u['id']}", headers=h,
                 json={"password": "newpass456", "is_active": True})
    assert client.post("/api/auth/login", json={
        "email": "cycle@test.cn", "password": "newpass456"}).status_code == 200


def test_users_org_isolation(client, other_org):
    h = auth_headers(client)
    mine = client.post("/api/users", headers=h, json={
        "email": "iso@test.cn", "name": "隔离", "password": "start12345",
        "role": "member"}).json()
    other = auth_headers(client, "owner2@test.cn")
    # 他司列表看不到、patch 404
    items = client.get("/api/users", headers=other).json()["items"]
    assert all(u["id"] != mine["id"] for u in items)
    assert client.patch(f"/api/users/{mine['id']}", headers=other,
                        json={"is_active": False}).status_code == 404
