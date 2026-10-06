"""Configuration readiness only; never probes a platform or claims a verified stream."""

import re

from live_review.integrations.capture.providers import CaptureRegistry


def provider_conditions(policy, platform):
    health = CaptureRegistry(policy).get(platform).health()
    blockers = []
    if not health["dependencies_ready"]:
        blockers.append({
            "code": "provider_dependencies_missing",
            "message": "抖音解析组件尚未配置，正在由开发人员处理。"
            if platform == "douyin" else "视频号投屏接收组件尚未配置。",
        })
    if platform not in policy.allowed_platforms:
        blockers.append({
            "code": "capture_platform_disabled",
            "message": "当前配置未开放视频号采集。"
            if platform == "wechat" else "当前配置未开放抖音采集。",
        })
    domains = policy.stream_domains
    configured = bool(domains) and all(
        re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", d)
        for d in domains
    )
    if not configured:
        blockers.append({
            "code": "capture_source_access_not_configured",
            "message": "直播来源访问尚未开放：允许访问的域名未配置，需先完成采集就绪复核。",
        })
    return health | {"source_access_configured": configured, "blockers": blockers}


def platform_conditions(policy, platform, execution, ffmpeg_ready, ffprobe_ready):
    result = provider_conditions(policy, platform)
    blockers = []
    if not policy.enabled:
        blockers.append({"code": "capture_not_configured", "message": "采集服务尚未启用。"})
    elif not execution["automatic_dispatch"]:
        blockers.append({
            "code": "capture_manual_execution",
            "message": "当前为手动执行模式，尚未接入页面自动采集。",
        })
    elif not execution["ready"]:
        blockers.append({
            "code": "capture_executor_unavailable", "message": "采集执行器未就绪，请等待服务恢复。",
        })
    if not ffmpeg_ready or not ffprobe_ready:
        blockers.append({
            "code": "capture_media_tools_missing", "message": "录制或媒体校验组件尚未就绪。",
        })
    blockers.extend(result["blockers"])
    return result | {"start_ready": not blockers, "blockers": blockers}
