"""统一入口：鉴权、健康检查、向内部 Go 服务转发流式音频与网页。"""
import requests
from flask import request,Response,jsonify,stream_with_context,redirect

HOP={"connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailer","transfer-encoding","upgrade"}

def register_gateway(app,engine):
    from auth import register_auth
    required=register_auth(app)
    @app.get("/healthz")
    def health():
        ok=engine.healthy()
        return jsonify(status="ok" if ok else "degraded",engine=ok),200 if ok else 503
    @app.route("/music",methods=["GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"])
    @app.route("/music/",methods=["GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"])
    @app.route("/music/<path:subpath>",methods=["GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS"])
    def music_proxy(subpath=""):
        if not subpath and request.method in ("GET","HEAD"):
            return redirect("/")
        # 目的地址只来自服务端配置；客户端认证头和内部令牌绝不原样转发。
        headers={k:v for k,v in request.headers if k.lower() not in HOP|{"authorization","x-music-hub-token","content-length"}}
        headers["Host"]=request.host
        # 统一入口开启鉴权后，已登录用户可管理引擎；关闭时保留引擎原有管理员鉴权。
        if required:headers["X-Music-Hub-Token"]=engine.token
        url=engine.base_url+request.path
        if request.query_string:url+="?"+request.query_string.decode("ascii")
        client=requests.Session()
        client.trust_env=False  # 内部服务不经过宿主机 HTTP_PROXY，且不同用户不共享 Cookie jar。
        try:
            upstream=client.request(request.method,url,headers=headers,data=request.get_data(),
                                      stream=True,allow_redirects=False,timeout=(5,180))
        except requests.RequestException:
            client.close()
            return jsonify(error="下载服务暂时不可用"),502
        excluded=HOP|{"set-cookie"}
        connection_tokens={x.strip().lower() for x in upstream.headers.get("Connection","").split(",")}
        response_headers=[(k,v) for k,v in upstream.headers.items() if k.lower() not in excluded|connection_tokens]
        # 多个 Set-Cookie 必须分开，音频的 Range / Content-Length / Content-Encoding 保持原样。
        for cookie in upstream.raw.headers.getlist("Set-Cookie"):response_headers.append(("Set-Cookie",cookie))
        if upstream.is_redirect:
            # requests 为准备下一次请求会先消费跳转正文，不能再从 raw 重复读取。
            body=upstream.content
            upstream.close();client.close()
            response_headers=[(k,v) for k,v in response_headers if k.lower() not in {"content-length","content-encoding"}]
            return Response(body,status=upstream.status_code,headers=response_headers)
        def chunks():
            try:
                yield from upstream.raw.stream(65536,decode_content=False)
            finally:
                upstream.close()
                client.close()
        response=Response(stream_with_context(chunks()),status=upstream.status_code,headers=response_headers,direct_passthrough=True)
        response.call_on_close(upstream.close)
        response.call_on_close(client.close)
        return response
