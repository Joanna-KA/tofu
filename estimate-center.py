import argparse
import numpy as np
from gi.repository import Ufo

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--input-directory', metavar='PATH', type=str, default='.',
                        help="Location with sinograms")
    parser.add_argument('-f', '--first', type=int, default=0,
                        help="First sinogram to use")
    parser.add_argument('-l', '--last', type=int, default=1000,
                        help="Last sinogram to use")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-s', '--angle-step', metavar='F', type=float,
                       help="Angle step between projections")
    group.add_argument('-p', '--num-projections', metavar='N', type=int,
                       help="Number of projections")

    args = parser.parse_args()

    # create nodes
    pm = Ufo.PluginManager()
    sino_reader = pm.get_filter('reader')
    cor = pm.get_filter('centerofrotation')

    # configure nodes
    count = args.last - args.first
    sino_reader.set_properties(path=args.input_directory, nth=args.first, count=count)

    angle_step = args.angle_step if args.angle_step else np.pi / args.num_projections
    cor.set_properties(angle_step=angle_step)

    centers = []

    def print_center(cor, prop):
        center = cor.props.center
        print 'Calculated center: %f' % center
        centers.append(center)

    cor.connect('notify::center', print_center)

    g = Ufo.Graph()
    g.connect_filters(sino_reader, cor)

    s = Ufo.Scheduler()
    s.run(g)

    print 'Mean center: %f' % np.mean(centers)