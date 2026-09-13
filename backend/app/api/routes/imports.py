"""Product import routes: template download, preview (validate), commit."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...deps import OrgScope, get_scope
from ...services.audit import audit
from ...services.imports import STANDARD_FIELDS, auto_map, build_preview, commit_preview, parse_table

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/template")
def download_template():
    """Sample CSV template beginners can fill and import directly."""
    header = ("sku,中文名称,英文名称,类别,材质,规格,颜色,包装,起订量,阶梯价格,币种,"
              "交期,认证,定制,供应商\n")
    sample = ("TS-BT-001,保温杯,Vacuum Insulated Bottle 500ml,保温杯,304不锈钢,500ml,黑色;白色,彩盒,500,"
              "500:3.2;1000:3.0;5000:2.8,USD,25,\"FDA, LFGB\",丝印 Logo,永康市XX五金厂\n"
              "TS-MG-001,陶瓷马克杯,Ceramic Coffee Mug 350ml,马克杯,陶瓷,350ml,白色,白盒+彩盒,1000,"
              "1000:1.1;3000:0.98,USD,20,CA Prop 65,印花+激光雕刻,潮州市XX陶瓷有限公司\n")
    from fastapi import Response
    return Response(content="\ufeff" + header + sample, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=tradesense_import_template.csv"})


@router.post("/preview")
async def preview(file: UploadFile = File(...),
                  mapping_json: str = Query("", alias="mapping"),
                  scope: OrgScope = Depends(get_scope), db: Session = Depends(get_db)):
    size_limit = 10 * 1024 * 1024
    content = await file.read()
    if len(content) > size_limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail={"code": "file_too_large", "message": "文件超过 10MB 限制"})
    name = file.filename or "upload.csv"
    if not name.lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "bad_type", "message": "仅支持 CSV / XLSX 文件"})
    mapping = None
    if mapping_json:
        import json
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail={"code": "bad_mapping", "message": "mapping 不是合法 JSON"})
    try:
        preview = build_preview(db, scope.org_id, content, name, mapping)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail={"code": "parse_error", "message": str(e)})
    out = preview.summary()
    # include suggested mapping fix (auto_map always available)
    try:
        headers, _ = parse_table(content, name)
    except Exception:  # noqa: BLE001
        headers = preview.columns
    out["suggested_mapping"] = auto_map(headers)
    out["standard_fields"] = STANDARD_FIELDS
    return out


@router.post("/commit")
def commit(token: str = Query(..., min_length=8), scope: OrgScope = Depends(get_scope),
           db: Session = Depends(get_db)):
    try:
        result = commit_preview(db, scope.org_id, token)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"code": "token_invalid", "message": str(e)})
    audit(db, scope.org_id, scope.user.id, "import.commit", "import", token,
          {"created": result["created"], "updated": result["updated"],
           "failed_rows": len(result["failed"])})
    db.commit()
    return result
