#!/usr/bin/env python3
import sys; sys.setrecursionlimit(20000)
"""Natural Earth 50m land -> inline SVG for SubSentry situation map.

Region: East Asia / Western Pacific (lon 105-149, lat 14.5-42.5), Web Mercator.
Outputs: map_land.svg (path fragments) + projected coords for key points.
"""
import json, math

LON0, LON1 = 112.5, 146.0
LAT0, LAT1 = 17.5, 41.5
W = 400.0  # viewBox width

def merc_y(lat):
    return math.log(math.tan(math.pi/4 + math.radians(lat)/2))

X0, X1 = math.radians(LON0), math.radians(LON1)
Y0, Y1 = merc_y(LAT0), merc_y(LAT1)
S = W / (X1 - X0)
H = (Y1 - Y0) * S

def project(lon, lat):
    x = (math.radians(lon) - X0) * S
    y = (Y1 - merc_y(lat)) * S
    return x, y

# ---- Sutherland-Hodgman clip against bbox (in lon/lat space) ----
def clip_poly(pts):
    def clip_edge(pts, inside, intersect):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i+1) % n]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
                if not ib: out.append(intersect(a, b))
            elif ib:
                out.append(intersect(a, b))
        return out
    def ix_v(x):  # vertical line lon=x
        def f(a, b):
            t = (x - a[0]) / (b[0] - a[0])
            return (x, a[1] + t*(b[1]-a[1]))
        return f
    def ix_h(y):
        def f(a, b):
            t = (y - a[1]) / (b[1] - a[1])
            return (a[0] + t*(b[0]-a[0]), y)
        return f
    pts = clip_edge(pts, lambda p: p[0] >= LON0, ix_v(LON0))
    if not pts: return []
    pts = clip_edge(pts, lambda p: p[0] <= LON1, ix_v(LON1))
    if not pts: return []
    pts = clip_edge(pts, lambda p: p[1] >= LAT0, ix_h(LAT0))
    if not pts: return []
    pts = clip_edge(pts, lambda p: p[1] <= LAT1, ix_h(LAT1))
    return pts

# ---- RDP simplify (projected space) ----
def rdp(pts, eps):
    if len(pts) < 3: return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx-ax, by-ay
    norm = math.hypot(dx, dy)
    dmax, idx = -1.0, 0
    for i in range(1, len(pts)-1):
        px, py = pts[i]
        if norm < 1e-9:
            d = math.hypot(px-ax, py-ay)  # 首尾同点：用到端点的距离
        else:
            d = abs(dy*px - dx*py + bx*ay - by*ax) / norm
        if d > dmax: dmax, idx = d, i
    if dmax > eps:
        left = rdp(pts[:idx+1], eps)
        right = rdp(pts[idx:], eps)
        return left[:-1] + right
    return [pts[0], pts[-1]]

def rdp_ring(ring, eps):
    """闭合环：从起点最远处切成两段分别 RDP，避免首尾重合退化。"""
    x0, y0 = ring[0]
    far = max(range(1, len(ring)), key=lambda i: (ring[i][0]-x0)**2 + (ring[i][1]-y0)**2)
    a = rdp(ring[:far+1], eps)
    b = rdp(ring[far:] + [ring[0]], eps)
    return a[:-1] + b[:-1]

def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]; x2, y2 = pts[(i+1) % len(pts)]
        a += x1*y2 - x2*y1
    return abs(a) / 2

gj = json.load(open('ne_50m_land.geojson'))
paths = []
total_pts = 0
for feat in gj['features']:
    geom = feat['geometry']
    polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
    for poly in polys:
        ring = poly[0]  # outer ring only
        # quick bbox reject
        lons = [p[0] for p in ring]; lats = [p[1] for p in ring]
        if max(lons) < LON0 or min(lons) > LON1 or max(lats) < LAT0 or min(lats) > LAT1:
            continue
        clipped = clip_poly([(p[0], p[1]) for p in ring])
        if len(clipped) < 3: continue
        proj = [project(*p) for p in clipped]
        if poly_area(proj) < 3.0:  # drop specks < 3 px^2
            continue
        simp = rdp_ring(proj, 0.55)
        if len(simp) < 3: continue
        total_pts += len(simp)
        d = 'M' + 'L'.join(f'{x:.1f} {y:.1f}' for x, y in simp) + 'Z'
        paths.append(d)

svg_land = '<path class="map-land" d="' + ' '.join(paths) + '"/>'

# ---- graticule ----
grat = []
for lon in range(115, 146, 10):
    x, _ = project(lon, 20)
    grat.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{H:.1f}"/>')
for lat in range(20, 42, 10):
    _, y = project(120, lat)
    grat.append(f'<line x1="0" y1="{y:.1f}" x2="{W:.1f}" y2="{y:.1f}"/>')
svg_grat = '<g class="map-grat">' + ''.join(grat) + '</g>'

# ---- cable routes (Catmull-Rom -> cubic Bezier through projected waypoints) ----
def catmull(pts):
    P = [project(*p) for p in pts]
    if len(P) == 2:
        (x0, y0), (x1, y1) = P
        return f'M{x0:.1f} {y0:.1f}L{x1:.1f} {y1:.1f}'
    d = f'M{P[0][0]:.1f} {P[0][1]:.1f}'
    ext = [P[0]] + P + [P[-1]]
    for i in range(1, len(ext)-2):
        p0, p1, p2, p3 = ext[i-1], ext[i], ext[i+1], ext[i+2]
        c1 = (p1[0] + (p2[0]-p0[0])/6, p1[1] + (p2[1]-p0[1])/6)
        c2 = (p2[0] - (p3[0]-p1[0])/6, p2[1] - (p3[1]-p1[1])/6)
        d += f'C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}'
    return d

CHONGMING = (121.85, 31.55)
NANHUI = (121.95, 30.88)
# 对端登陆点（海缆终点必须精确落在这些点上）
BUSAN   = (129.05, 35.0)    # 釜山
CHIBA   = (139.9, 34.9)     # 千叶（TPE/NCP S1.1）
IBARAKI = (140.55, 36.1)    # 茨城（NCP S3）
TOUCHENG = (121.87, 24.97)  # 头城
HONGKONG = (114.3, 22.28)   # 香港

cables = {
  # id: waypoints (lon,lat)。出发扇面按方位角梳理，途经点走海上，终点=登陆点
  'APG_S3':    [CHONGMING, (124.8, 33.6), BUSAN],                                   # 韩/日（北侧走廊）
  'APCN2_S4A': [CHONGMING, (124.2, 32.9), BUSAN],                                   # 韩/日（南侧走廊）
  'NCP_S1_1':  [CHONGMING, (128.5, 31.9), (134.5, 32.6), CHIBA],                    # 日/美
  'TPE_S1S':   [CHONGMING, (127.5, 30.7), (133.5, 31.5), (138.9, 33.9), CHIBA],     # 日/美
  'NCP_S3':    [NANHUI, (127.0, 29.2), (134.5, 30.5), (140.3, 33.6), IBARAKI],      # 日/美（东南绕行→茨城）
  'TPE_S4':    [CHONGMING, (122.7, 28.5), TOUCHENG],                                # 台/日
  'APCN2_S3':  [CHONGMING, (122.6, 27.6), (118.4, 23.2), HONGKONG],                 # 港/美
  'APG_S4':    [NANHUI, (121.5, 26.8), (117.5, 21.0), (113.4, 17.5)],               # 日/新（出图）
}
for cid, wps in cables.items():
    print(f'{cid}: d="{catmull(wps)}"')

pts = {
  '崇明': CHONGMING, '南汇': NANHUI,
  '釜山': BUSAN, '千叶': CHIBA, '茨城': IBARAKI, '头城': TOUCHENG, '香港': HONGKONG,
  'lab_中国大陆': (114.5, 33.5), 'lab_日本': (136.6, 36.4), 'lab_韩国': (127.3, 36.6),
  'lab_台湾': (120.8, 23.8), 'lab_香港': (113.9, 21.35),
  'lab_黄海': (122.8, 35.6), 'lab_东海': (124.8, 29.3), 'lab_太平洋': (141.5, 25.5),
}
for name, p in pts.items():
    x, y = project(*p)
    print(f'{name}: {x:.1f},{y:.1f}')

print(f'\nviewBox: 0 0 {W:.0f} {H:.1f}  polys={len(paths)} pts={total_pts} land_bytes={len(svg_land)}')
open('map_land_fragment.txt', 'w').write(svg_grat + '\n' + svg_land)
