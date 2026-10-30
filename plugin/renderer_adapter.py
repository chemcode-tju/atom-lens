"""Small, checked fixes for the pinned 3Dmol renderer's resize lifecycle."""


def resize_safe_renderer(source: str) -> str:
    """Reuse GPU objects and avoid assigning unchanged canvas dimensions.

    Assigning canvas.width/height clears its drawing buffer, even when the value
    is unchanged. Upstream updateSize also calls setSize twice. Framebuffer
    storage is already resized by setFrameBuffer at draw time, so its object
    handles and shader programs should be initialized only once per renderer.
    """
    replacements = [
        ('window.addEventListener("resize",this.resize.bind(this))',
         'this.config.manualResize||window.addEventListener("resize",this.resize.bind(this))'),
        ('void 0!==window.ResizeObserver&&(this.divwatcher=',
         '!this.config.manualResize&&void 0!==window.ResizeObserver&&(this.divwatcher='),
        ('updateSize(){this.renderer.setSize(this.WIDTH,this.HEIGHT),this.ASPECT=',
         'updateSize(){this.ASPECT='),
        ('this._canvas.width=e*this.devicePixelRatio,this._canvas.height=t*this.devicePixelRatio,',
         'this._canvas.width!==Math.floor(e*this.devicePixelRatio)&&(this._canvas.width=Math.floor(e*this.devicePixelRatio)),this._canvas.height!==Math.floor(t*this.devicePixelRatio)&&(this._canvas.height=Math.floor(t*this.devicePixelRatio)),'),
        ('initFrameBuffer(){if(this.isWebGL1())return;',
         'initFrameBuffer(){if(this.isWebGL1()||this._fb)return;'),
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError("Pinned renderer changed; review resize adapter before updating")
        source = source.replace(old, new)
    return source


def studio_lighting_renderer(source: str) -> str:
    """Soft fill and a weak broad highlight, shared by preview/export shaders.

    Sphere imposters shadow the varying named vLight with diffuse intensity.
    Use a camera-space half vector for specular, never that shadowed value.
    This is raster lighting, not ambient occlusion or ray-traced shadows.
    """
    highlight = " + vec3(0.04 * pow(max(dot(norm, normalize(vec3(-0.45,0.65,2.27))), 0.0), 10.0))"
    replacements = [
        ("vec3 color = vLight*vColor;",
         "vec3 color = (vec3(0.34) + 0.62*vLight)*vColor" + highlight + ";"),
        ("color *= light;",
         "color = color*(vec3(0.34) + 0.62*light)" + highlight + ";"),
    ]
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError("Pinned renderer changed; review lighting adapter before updating")
        source = source.replace(old, new)
    return source
