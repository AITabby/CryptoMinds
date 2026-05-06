# flake8: noqa
"""
CryptoMinds API — Protocol info blueprint (3 routes)
"""

from flask import Blueprint, jsonify
from protocol import get_protocol_info, ChannelRegistry, GateRegistry

protocol_bp = Blueprint("protocol", __name__, url_prefix="/api/v1")


@protocol_bp.route("/info", methods=["GET"])
def api_info():
    return jsonify(get_protocol_info())


@protocol_bp.route("/channels", methods=["GET"])
def api_channels():
    return jsonify(ChannelRegistry.list_all())


@protocol_bp.route("/gates", methods=["GET"])
def api_gates():
    return jsonify(GateRegistry.list_all())
