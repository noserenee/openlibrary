import 'slick-carousel';
import '../../../../static/css/components/carousel--js.less';
import Carousel from './carousel/Carousel';

export function initPartials() {
    jQuery(window).load(function () {
        $.ajax({
            url: '/partials',
            type: 'GET',
            data: {
                workid: $('.RelatedWorksCarousel').attr('workId'),
                _component: true
            },
            datatype: 'json',
            success: function (response) {
                $('.RelatedWorksCarousel').append(response[0]);
                const $carouselElements = $('.RelatedWorksCarousel .carousel--progressively-enhanced');
                if ($carouselElements.length) {
                    $carouselElements.each(function (_i, carouselElement) {
                        Carousel.add.apply(
                            Carousel,
                            JSON.parse(carouselElement.dataset.config)
                        );
                    });
                }
            }
        });
    });
}
