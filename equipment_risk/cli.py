import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from .generator import generate_dataset
from .validation import validate_dataset
from .evaluation import evaluate

def checksums(path):
    result={}
    for f in sorted(Path(path).glob("*.csv")):
        h=hashlib.sha256()
        with f.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):
                h.update(chunk)
        result[f.name]=h.hexdigest()
    return result

def main():
    parser=argparse.ArgumentParser(description="Synthetic equipment failure risk analytics")
    sub=parser.add_subparsers(dest="command",required=True)
    g=sub.add_parser("generate"); g.add_argument("--scale",choices=["starter","full"],default="starter")
    g.add_argument("--seed",type=int,default=20261022); g.add_argument("--readings",type=int)
    g.add_argument("--days",type=int,default=90); g.add_argument("--out",default="data/starter")
    v=sub.add_parser("validate"); v.add_argument("--input",required=True)
    e=sub.add_parser("evaluate"); e.add_argument("--input",required=True)
    r=sub.add_parser("reproducibility"); r.add_argument("--scale",choices=["starter","full"],default="starter")
    r.add_argument("--seed",type=int,default=20261022)
    args=parser.parse_args()
    if args.command=="generate":
        generate_dataset(args.out,args.scale,args.seed,args.readings,args.days)
        validate_dataset(args.out); evaluate(args.out)
        path=Path(args.out); (path/"checksums.json").write_text(json.dumps(checksums(path),indent=2),encoding="utf-8")
        print(f"Generated {args.scale} dataset in {path.resolve()}")
    elif args.command=="validate":
        print(json.dumps(validate_dataset(args.input),indent=2))
    elif args.command=="evaluate":
        print(json.dumps(evaluate(args.input),indent=2))
    elif args.command=="reproducibility":
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a"; b=Path(tmp)/"b"
            generate_dataset(a,args.scale,args.seed); generate_dataset(b,args.scale,args.seed)
            ca,cb=checksums(a),checksums(b)
            comparable_a={k:v for k,v in ca.items() if k not in ("run_metadata.json",)}
            comparable_b={k:v for k,v in cb.items() if k not in ("run_metadata.json",)}
            result={"seed":args.seed,"checksums_match":comparable_a==comparable_b,
                    "first_checksums":comparable_a,"second_checksums":comparable_b}
            print(json.dumps(result,indent=2))
            if comparable_a != comparable_b: sys.exit(1)
if __name__=="__main__": main()
