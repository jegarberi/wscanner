#!/usr/bin/env python3
# Entrena un splat 3D con los fotogramas que sube el escáner (/data/<sesión>/manifest.json).
# Genera /data/<sesión>/splat.ply en formato 3DGS estándar. Sin densificación todavía.
import glob
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from gsplat import rasterization

DATA = os.environ.get("DATA_DIR", "/data")
ITERS = int(os.environ.get("ITERS", "3000"))
MAX_SIDE = int(os.environ.get("MAX_SIDE", "960"))  # lado máximo de entrenamiento (memoria)
C0 = 0.28209479177387814  # constante SH de grado 0
dev = torch.device("cuda")


def load_session(folder):
    m = json.load(open(os.path.join(folder, "manifest.json")))
    s = min(1.0, MAX_SIDE / max(m["w"], m["h"]))
    w, h, f = round(m["w"] * s), round(m["h"] * s), m["focal"] * s
    views = []
    for fr in m["frames"]:
        path = os.path.join(folder, fr["name"])
        if not os.path.exists(path):
            continue
        img = Image.open(path).convert("RGB").resize((w, h), Image.BILINEAR)
        gt = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255).to(dev)
        # ejes mundiales del escáner: r derecha, u arriba, d hacia atrás → cámara OpenCV: x=r, y=-u, z=-d
        r, u, d = (torch.tensor(fr[k], dtype=torch.float32) for k in ("r", "u", "d"))
        Rc2w = torch.stack([r, -u, -d], dim=1)
        c = torch.tensor(fr["c"], dtype=torch.float32)
        V = torch.eye(4)
        V[:3, :3] = Rc2w.T
        V[:3, 3] = -Rc2w.T @ c
        views.append((V.to(dev), gt))
    K = torch.tensor([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=torch.float32, device=dev)
    return m, w, h, K, views


def init_params(m):
    pts = np.array(m.get("points", []), dtype=np.float32)
    if len(pts) >= 100:
        xyz, rgb = pts[:, :3], pts[:, 3:6] / 255
    else:  # sin puntos triangulados: nube aleatoria alrededor de las cámaras
        cs = np.array([fr["c"] for fr in m["frames"]], dtype=np.float32)
        xyz = np.random.uniform(cs.min(0) - 0.5, cs.max(0) + 0.5, (20000, 3)).astype(np.float32)
        rgb = np.full((len(xyz), 3), 0.5, dtype=np.float32)
    n = len(xyz)
    extent = float(np.linalg.norm(xyz.max(0) - xyz.min(0))) + 1e-6
    s0 = 0.5 * extent / n ** (1 / 3)  # tamaño ≈ separación media entre puntos
    p = {
        "mu": torch.nn.Parameter(torch.tensor(xyz, device=dev)),
        "q": torch.nn.Parameter(torch.tensor([1.0, 0, 0, 0], device=dev).repeat(n, 1)),
        "s": torch.nn.Parameter(torch.full((n, 3), float(np.log(s0)), device=dev)),
        "o": torch.nn.Parameter(torch.full((n,), 0.0, device=dev)),  # opacidad 0.5 en logit
        "c": torch.nn.Parameter(torch.tensor((rgb - 0.5) / C0, device=dev)[:, None, :]),
    }
    lr = {"mu": 1.6e-4 * extent, "q": 1e-3, "s": 5e-3, "o": 5e-2, "c": 2.5e-3}
    opt = torch.optim.Adam([{"params": [p[k]], "lr": lr[k]} for k in p])
    return p, opt


def render(p, V, K, w, h):
    out, _, _ = rasterization(
        means=p["mu"], quats=F.normalize(p["q"], dim=-1), scales=torch.exp(p["s"]),
        opacities=torch.sigmoid(p["o"]), colors=p["c"], viewmats=V[None], Ks=K[None],
        width=w, height=h, sh_degree=0,
    )
    return out[0]


def save_ply(path, p):
    mu = p["mu"].detach().cpu().numpy()
    names = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
             "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    cols = [mu, np.zeros((len(mu), 3), np.float32), p["c"].detach().cpu().numpy().reshape(-1, 3),
            p["o"].detach().cpu().numpy()[:, None], p["s"].detach().cpu().numpy(),
            F.normalize(p["q"].detach(), dim=-1).cpu().numpy()]
    data = np.concatenate(cols, axis=1).astype("<f4")
    header = "ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % len(mu)
    header += "".join("property float %s\n" % k for k in names) + "end_header\n"
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(header.encode())
        f.write(data.tobytes())
    os.replace(tmp, path)


def train_session(folder):
    t0 = time.time()
    m, w, h, K, views = load_session(folder)
    if len(views) < 2:
        raise RuntimeError("se necesitan al menos 2 fotogramas, hay %d" % len(views))
    p, opt = init_params(m)
    for it in range(ITERS):
        V, gt = views[np.random.randint(len(views))]
        loss = (render(p, V, K, w, h).clamp(0, 1) - gt).abs().mean()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if it % 500 == 0 or it == ITERS - 1:
            print(f"{os.path.basename(folder)} it {it}/{ITERS} L1 {loss.item():.4f} gaussianas {len(p['mu'])}", flush=True)
    # poda: las gaussianas casi transparentes se quitan antes de exportar (si no, el visor se queda en «Processing splats»)
    keep = torch.sigmoid(p["o"].detach()) >= 0.01
    p = {k: v.detach()[keep] for k, v in p.items()}
    print(f"{os.path.basename(folder)}: gaussianas tras la poda {int(keep.sum())}", flush=True)
    save_ply(os.path.join(folder, "splat.ply"), p)
    print(f"{os.path.basename(folder)}: listo en {time.time() - t0:.0f} s", flush=True)


def pending():
    for mf in sorted(glob.glob(os.path.join(DATA, "*", "manifest.json"))):
        d = os.path.dirname(mf)
        if not os.path.exists(os.path.join(d, "splat.ply")) and not os.path.exists(os.path.join(d, "error.txt")):
            yield d


if __name__ == "__main__":
    print("entrenador listo, iteraciones:", ITERS, flush=True)
    while True:
        for d in list(pending()):
            try:
                train_session(d)
            except Exception as e:  # una sesión mala no debe bloquear las demás
                print("error en", d, e, flush=True)
                with open(os.path.join(d, "error.txt"), "w") as f:
                    f.write(str(e))
        time.sleep(10)
