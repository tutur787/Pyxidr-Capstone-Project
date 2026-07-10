import logging
from fastapi import APIRouter
from services.bigquery_service import get_fabn_list

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fabns", tags=["fabns"])


@router.get("")
def list_fabns():
    return get_fabn_list()
