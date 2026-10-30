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
